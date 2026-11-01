# 把防抖收进影子插件 — 设计与交接

> 状态：**P2（静默窗口）与 P3（抗掐断重试）已实现并部署在插件侧**（插件仓 v0.3.10）。
> 决策人：负责人（2026-10-31 23:35）。定调：**不图省事，做对**。
> 2026-11-01 补：离线实测结论见 §9，**未动 core**。

## 1. 要解决的其实是三件事

负责人一句话「影子插件自己处理防抖」底下压着三个不同的问题，**必须分开处理**，混在一起就会设计出错误的开关。

| # | 问题 | 性质 | 现状 |
|---|---|---|---|
| **P1** | 用户连发多条 → 判定器被触发多次 | 策略 | **已有解**：`_await_batch`（`main.py:1267`）+ `batch_preset`，默认 off |
| **P2** | 判定通过后、生成前群里又有人说话 → 机器人抢答 | 策略 | **无解，需新增** |
| **P3** | 外部防抖插件（debounce）把主动回复的 LLM 请求掐掉 | **bug** | **无解，需新增** |

P1 和 P2 是"防抖"，可以做成开关；**P3 是 bug，不该做成开关**——它必须默认修好，否则用户一关防抖，主动回复又开始丢。

## 2. 证据（不要重新查，已核实）

- **P3 实证**：6 小时运行里 **9 次 REPLY 只有 7 次 `已发送`**，差 2 次。两次都发生在 `debounce - on_llm_request stopped event propagation` 之后 3 ms。
- 掐断链：debounce 在 `on_llm_request` 上 `stop_event()` → 事件生成器 `GeneratorExit` → 插件 `await` 链被打断 → 整个发送流程消失。
- **已修的只是副作用**：`reset_current_plugin` 跨 Context 的 `ValueError`（提交 `19c42b42a`）修的是崩溃，**没有修"回复被吞"**。P3 仍然活着。
- `debounce` 的 4 处 `stop_event()` **就是防抖本体**（main.py 385/395/503/537，全是"消息不完整 → 掐掉当前调用、塞进 buffer 等合并"）⇒ **不可能只关掐断保留防抖**。
- 配置里的 `cancel_on_new_message` **是死键**，debounce 的 main.py 里零引用，调它无效。
- 上游 `RateLimitStage` 是 Fixed Window 限流（只延后、不合并），**不是防抖的替代品**，这条路走不通。

## 3. 设计

### 3.1 配置（新增到 `_conf_schema.json`）

```
debounce.enabled               bool  默认 false   # 影子插件自管防抖；关掉则由外部插件管
debounce.quiet_sec             float 默认 1.5     # 判定通过后、生成前的群静默窗口
debounce.retry_when_cancelled  bool  默认 true    # 生成被外部插件掐断时重试（修 P3）
```

`retry_when_cancelled` **默认开且独立于 `enabled`**——它修的是 bug。

### 3.2 逻辑

**P2（静默窗口）**，仅在 `debounce.enabled` 为真时生效：

判定返回 REPLY 之后、调 `_generate_persona` 之前，看该群 `unified_msg_origin` 最后一次消息到达时间；若距今不足 `quiet_sec`，就 `await` 等到静默（或达到上限），期间若来新消息则重新计。等完再生成。

> 这条顺手解决待办 #1 的抢答：上次有人 3 秒前答了"会"，机器人第 6 秒还插嘴。

**P3（抗掐断）**，与 `enabled` 无关，默认执行：

```
resp = generate_with_persona(...)
if resp is None:                    # 被某个 on_llm_request 钩子掐断
    event.continue_event()          # 撤销 stop，恢复事件
    await asyncio.sleep(小抖动)
    resp = generate_with_persona(...)  # 再试一次
```

`continue_event()` 是 `stop_event()` 的逆操作（已核实存在，`astr_message_event.py:376`），会重置 `_force_stopped` 与 `MessageEventResult`。**这是重试方案成立的前提。**

⚠️ **已知风险（未验证，实施时必须先做这一步）**：重试时 debounce 可能**再次掐断**，因为它的判断基于"消息完整性"，与时间无关。若实测重试仍被掐，需要一条降级路径——第二次尝试**不派发 `on_llm_request` 钩子**（丢掉 livingmemory / enhance_mode 的注入，人格不受影响，因为 `proactive_persona.py` 自己注入人格）。

降级路径需要 core 侧给 `generate_with_persona` 加一个可选参数（默认 `True`，零行为变化，属 additive）：

```python
async def generate_with_persona(..., dispatch_llm_request_hook: bool = True) -> ...:
    if dispatch_llm_request_hook:
        if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
            return None
```

**先实测重试够不够用，够用就不要动 core。** 动 core 意味着同步台账（`maintained/installed_manifest.json` 的 SHA-256）、补 `tests/maintained/` 测试、`apply_patches` 部署、重启。

## 4. 关键代码位置

插件仓 `D:/astrbot_plugin_proactive_shadow/main.py`（v0.3.9，1556 行）：

| 位置 | 作用 |
|---|---|
| `1267 _await_batch` | **先读它**。P1 的现有实现，别重复造轮子 |
| `1243 _resolve_batch_preset` | batch 开关解析 |
| `1332 on_group_message` | 主流程入口（225 行 / 37 分支，改动位置要慎重选） |
| `1019 _generate_persona` | 生成，返回 `(text, tagged)`；**失败路径众多，见避坑** |
| `754 _maybe_send` | 发送 |
| `119 dataclass _Batch` | 批处理状态 |

core（`D:/asbot_core_for_fork`）：

| 位置 | 作用 |
|---|---|
| `astrbot/core/proactive_persona.py:110` | `call_event_hook(event, OnLLMRequestEvent, req)`，被掐点 |
| `astrbot/core/platform/astr_message_event.py:368/376` | `stop_event` / `continue_event` |
| `astrbot/core/pipeline/context_utils.py:103` | `call_event_hook`，返回 True = 被终止 |

## 5. ★ 避坑清单（按踩坑代价排序）

1. **`_generate_persona` 返回 `("", "")` 有 7 种原因，重试只对其中 1 种有意义**：
   `persona_enabled` 关 / 导入失败 / 超时 / 异常 / `raw_text` 空 / `<refuse/>` / `[SKIP]` 弃权。
   **其中 `<refuse/>` 和 `[SKIP]` 是主动弃权——重试它们是错的**（会逼模型重新输出它刚拒绝的内容）。
   只能对"被钩子掐断"这一路重试，所以需要区分，不能无脑重试。

2. **不要动第三方 debounce 的源码**。它更新会被覆盖。要关就用它自己的 `enabled` 开关（已验证生效：两个 handler 开头都是 `if not self.config.get("enabled", True): return`）。

3. **改实例配置不会热更新**，需要重启 AstrBot 或重载插件才生效。改完必须重启验证，不能只看文件。

4. **`on_group_message` 是 225 行 / 37 分支的大函数**，历史上曾因插入位置出事故（见项目记忆）。新增逻辑优先放在独立方法里由它调用，不要往中间塞。

5. **P1 已有 `batch_preset`**，默认 off 是有意为之（CHANGELOG 0.3.0：实测即使 2700 人群，判定的中位间隔也有 58 秒，批处理只在"亚 2 秒间隔占比 > 15%"时才划算）。**不要顺手把默认改掉**，那是另一个决策。

6. 日志级别是 **`[ERRO]` 不是 `[ERROR]`**。统计错误时两个都要搜，否则得出"零错误"的假象（本项目踩过）。

7. 插件测试命令（必须带 `PYTHONPATH`）：
   ```
   TMP=/d/pytest_tmp TEMP=/d/pytest_tmp PYTHONDONTWRITEBYTECODE=1 \
   PYTHONPATH="D:/asbot_core_for_fork;D:/astrbot_plugin_proactive_shadow" \
   ~/.workbuddy/binaries/python/envs/astrbot-test/Scripts/python.exe \
     -m pytest tests -p no:cacheprovider -q
   ```
   基线 **72 passed**。改完必须仍全绿。

8. 部署链路：改完 → 同步 `main.py` 到实例插件目录 → 重启 → 看日志。
   实例插件目录：`<INST>/core/data/plugins/astrbot_plugin_proactive_shadow/`
   （注意：<INST>/data/plugins/ 是废弃的，生效的是 `<INST>/core/data/plugins/`）

9. **本方案默认不动 core，所以不需要动台账**。一旦决定加 `dispatch_llm_request_hook` 参数，就必须：改 `astrbot/core/proactive_persona.py`（在台账内）+ 同步 `maintained/installed_manifest.json` 的 SHA-256（**key 用正斜杠**，用反斜杠会新增重复条目 53→54）+ 补 `tests/maintained/` 测试 + `apply_patches --apply` + `check_drift` 双端 NO DRIFT。

## 6. 验收标准（必须可观测，不能只看代码）

| 项 | 及格线 |
|---|---|
| P3 | 连续运行 6 小时，**`REPLY` 次数 == `已发送` 次数**（现在是 9 vs 7） |
| P3 | 日志里 `debounce - on_llm_request stopped` 之后紧跟的回复不再消失 |
| P2 | 抢答减少：抽样 REPLY，确认没有"别人 3 秒内已回答"的情况 |
| 回归 | 插件测试 72 passed 保持；`[ERRO]` 无新增；主动回复的拟人质量不下降（抽样看内容，别只看条数） |

判据要能区分真假：`已发送` 少了也可能是"生成阶段弃权/拒绝"（正常），不是被掐。

**判据要按这个修正（2026-11-01）**：`REPLY == 已发送` **永远达不到**，合法弃权必然存在。
`_generate_persona` 的 7 条失败路径里，只有"被钩子掐断"是**一行日志都没有**的
（`resp is None → raw_text 空 → 直接 return`，插件 `main.py` 的 raw_text 判空处）；
其余 6 条都有 `生成阶段拒绝` / `生成阶段弃权` / `人格生成超时` / `人格生成失败`。
⇒ 真正的及格线是：**`REPLY − 已发送 − 生成阶段拒绝/弃权 == 0`**。
实测样本（debounce 关闭后 2h09m）：REPLY 4 / 已发送 2 / 拒绝 1 / **被掐 1**（21:37:17，
debounce `stopped event propagation` 后 4 ms 记录 REPLY，无任何生成日志）。

## 7. 当前环境状态（2026-10-31 23:35）

- 电脑已重启，AstrBot **由 launcher 自动拉起**（PID 20976，6185/6199 在听）——不再是后台任务托管，好事。
- debounce 当前 **`enabled: false`**（已关），备份在
  `<INST>/core/data/config/astrbot_plugin_debounce_config.json.bak-before-disable`
- 实例插件是 **v0.3.9**（已含同秒去重）。`metadata.yaml` 的 version 字段长年写 v0.1.0，**不可用做版本判据**。
- core HEAD `62acfb13a`，已 push，远端 0/0。台账 53 条双端 NO DRIFT。
- 夜间流量低（凌晨 2 点后约 15 分钟才 42 条），**验证 P2/P3 最好在白天做**，夜里样本不够。

## 8. 给新会话的提示词（直接复制）

```text
继续 AstrBot 维护 fork 的任务：把防抖收进影子插件。

■ 先读（只读，不要改任何文件）：
1. D:/asbot_core_for_fork/docs/maintained/debounce-in-shadow.md  ← 本设计，含全部证据与避坑
2. D:/asbot_core_for_fork/.workbuddy/memory/2026-10-31.md        ← 昨天的完整上下文
3. D:/astrbot_plugin_proactive_shadow/main.py 的 1267 `_await_batch` 与 1332 `on_group_message`

■ 要做的三件事（P1 已有解，重点做 P2 和 P3）：
- P2：判定通过后、生成前加 `quiet_sec` 静默窗口（新配置，默认关）
- P3：生成被外部插件掐断时，`event.continue_event()` 撤销后重试（默认开，修 bug）
- 配置落在 `_conf_schema.json` 的 `debounce` 段，见设计 §3.1

■ 动手前必须先验证一件事：
重试时 debounce 会不会再次掐断（它的判断基于"消息完整性"，与时间无关）。
若会，才考虑给 core 的 generate_with_persona 加 dispatch_llm_request_hook 参数做降级。
**先确认重试够不够用，够用就不要动 core。**

■ 硬约束：
1. 不改第三方 debounce 源码；用户定调「插件解决 bug，而不是让 core 偏离」
2. 不动 core 就不需要动台账；一旦动 core，必须同步 installed_manifest.json 的 SHA-256
   （key 用正斜杠）、补 tests/maintained 测试、apply_patches、check_drift 双端 NO DRIFT
3. `_generate_persona` 返回 ("","") 有 7 种原因，只对"被钩子掐断"重试；
   <refuse/> 与 [SKIP] 是主动弃权，严禁重试（会逼模型重复它刚拒绝的内容）
4. 一改动一提交；改完必须有可观测验证（看日志计数），不能只看代码"看起来对"
5. 不要图省事——半年前别人看代码要能懂这处改动的意图

■ 验收：连续 6 小时 REPLY 次数 == 已发送次数（现在是 9 vs 7）；插件测试 72 passed 保持；
   [ERRO] 无新增。注意日志级别是 [ERRO] 不是 [ERROR]。

■ 环境：实例插件目录是 <INST>/core/data/plugins/（不是 <INST>/data/plugins/，那份废弃）；
   改配置需重启才生效；实例 <INST> =
   C:/Users/philia093/.astrbot_launcher/instances/83ca721d-26d2-4dd0-9932-ef9299d8829d

请先汇报你读到的状态和打算怎么验证「重试会不会再次被掐」，等我确认再动手。
```

> §8 是 2026-10-31 交给下一个会话的提示词，已执行完毕，保留作历史。

## 9. ★ 离线验证结果（2026-11-01）：**未动 core**

### 9.1 怎么验的

不碰实例配置、不重启、不改第三方源码：用实例 venv 的 python 真实
`import` 第三方 `DebouncePlugin`（`object.__new__` 绕过 `__init__`，手填状态，
`classifier` 换成固定分数的假分类器），**真跑 `on_llm_request`**，模拟
「掐断 → `continue_event()` → 重试 → 再来一条真实 @ 消息」。脚本（不入仓）：
`D:/tmp_verify/verify_debounce_retry.py`。

### 9.2 三个答案

| 问题 | 结果 |
|---|---|
| ① 重试会不会再被掐 | **不会**（`attempt2 stopped=False`） |
| ② `req.prompt` 会不会被劫持 | **会**：变成 `原文 原文`；若中间插了别人说话变成 `原文 别人的话 原文` |
| ③ 会不会污染下次真实回复 | **会**，而且**与是否被掐无关** |

① 的机理：`classifier_backend` 是 `onnx`，重试时 `should_merge` 因
`waiting_sessions` 为真，`buffer.add()` 把同一条消息**再加一遍**变成 2 条，
命中 debounce `main.py:438` 的 `len(buffer.messages) > 1 and backend != "jev"`
→ 合并直发、不再 `stop_event()`。**若用户把后端换成 `jev`，这条不成立，重试会被再掐。**

③ 的机理：请求一旦通过就 `pending_llm_sessions.add(session_id)`，而我们的路径
（`generate_with_persona`）**从不派发 `on_llm_response`** ⇒ 该集合永不清理 ⇒
该群下一条真实 @ 消息被 `on_waiting_llm_request:351` 标 `discard_next_response`
→ `on_llm_response:565` 把**正常回复清成空串**。场景 B（第一次就 pass、根本没被掐）
同样复现 ⇒ **这是"外部 debounce 开着"的固有代价，不是 P3 引入的**。

### 9.3 因此怎么定的

- 按负责人预设判据（"会不会再次掐断"）→ **不会** ⇒ **不动 core**，不加
  `dispatch_llm_request_hook` 参数，不动台账、不补 core 测试、不 `apply_patches`。
- ② 用**纯插件手法**化解：重试那一次把措辞指令**同时放进 `system_prompt`**——
  debounce 只改 `req.prompt`，`system_prompt` 是它不动的槽位，人格也在里面。
- ③ 不在本次修：它只在外部 debounce 开启时发生，而外部 debounce 当前是关的。
  **这条是已知债务**：将来若要重开外部 debounce，必须先解决它（正解是让主动回复
  不派发 `on_llm_request`，即 §3.2 的降级参数；或让该路径补派发 `on_llm_response`）。

### 9.4 落地位置（插件仓 v0.3.10）

- `_resolve_debounce()`：解析 `debounce` 段，返回 `(enabled, quiet_sec, retry_when_cancelled)`
- `_await_quiet(event, judged_at)`：静默窗口，返回"判定期间群里是否又有人说话"；
  仅 `debounce.enabled` 为真时生效，等待上限 4×`quiet_sec`
- `on_group_message`：判定后若群里又有人说话，重读历史并用同一套编号重建上下文
  （`_context_lines()`，避免两处编号漂移导致 `quote_n` 指错消息）
- `_persona_call()` + `_generate_persona` 里的重试：仅当
  `resp is None and event.is_stopped() and not was_stopped` 才重试一次
- 测试 `tests/test_debounce.py`（16 项）：插件 **88 passed**（原基线 72）

### 9.5 追记（2026-11-01 11:30）：静默窗口曾整日空转，已修

**症状**：上线 12 小时后复盘线上数据，`shadow_log.jsonl` 里 939 次 REPLY，
静默窗口命中 **0 次**；`astrbot.log` 里「判定期间群里有新消息」**0 条**、
「群里一直有人说话，不再等静默」**0 条**。也就是说 P2 一次都没真正生效。

**根因**：判定时间点在 `llm_generate` **返回之后**才取。

```python
resp = await asyncio.wait_for(self.context.llm_generate(...))
judged_at = time.monotonic()          # ← 判定已经结束
...
return self._last_msg_at[origin] > judged_at
```

判定**期间**到达的消息，其 `_last_msg_at` 必然小于 `judged_at`，于是永远被判成
「群里没动」。而代码上方注释写的是 *whether the group moved on **while the judge was
thinking*** —— 注释描述的正是代码看不见的那部分。**意图与实现错位，不是取舍问题。**

**修复**：取样点移到判定请求发出之前，参数改名 `judged_at` → `snapshot_at`，
语义变成「判定所依据的那份快照的时刻」。

**测试**：`tests/test_debounce.py` 新增两条，各管一半：
- `test_quiet_window_sees_a_message_that_arrived_while_thinking` —— 行为：
  消息在调用期间到达、且早于等待，窗口必须报告「动过了」。
- `test_the_snapshot_is_taken_before_the_judgement_request` —— 结构：用 `ast`
  解析 `on_group_message`，断言 `snapshot_at` 的赋值行在 `llm_generate` 调用行之前。
  行为测试是**显式传入**时间戳的，调用点改回原位它们照样绿，只有这条能拦住回退
  （已验证：把旧代码的标识符替换成 `snapshot_at` 后，这条断言会失败）。

插件 **102 passed**（原 100）。`ruff check` / `format --check` 均干净。

**修好之后要重新观察**，不能沿用旧结论：窗口会真的开始等待（上限 4×`quiet_sec`，
默认 6 秒），需要看两条日志的计数是否从 0 变成非 0，以及回复延迟的实际增量。
在拿到这组数据之前，`debounce.enabled` 保持现状（当前 `true`），不新增结论。
