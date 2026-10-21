# 主动回复项目 — 交接与下一步（供新对话使用）

> 写作时间：2026-10-21 23:00
> 目的：让新对话用**干净上下文 + 这份文档**直接续做，无需重新摸索。

## 0. 一句话状态

判定标准已经通过真实验证（372 条、6 个群、REPLY 7%、质量与泛化都合格），
原型以**影子模式**运行在实例内（只判定、不发送）。剩下的工作是：
补盲区 → 自动化测试 → 半开真发送 → 正式插件（主权、开源）。

## 1. 已完成（均有证据）

| 项 | 状态 | 证据 |
|---|---|---|
| 判定标准（来自用户标注的 10 个场景） | ✅ | `docs/maintained/proactive-design.md` |
| 影子模式插件 | ✅ 在跑 | 实例 `core/data/plugins/astrbot_plugin_proactive_shadow/` |
| 真群数据 | ✅ 372 条 / 6 群 | `shadow_log.jsonl` |
| REPLY 质量 | ✅ 全是实质增量，无纯情绪 | 见日志 `draft` 字段 |
| 泛化性 | ✅ 新群（不同游戏）同样合格 | 新群 225 条、11 次 REPLY |
| 健壮性 | ✅ 超时 25s + 连续失败暂停 300s | 修复前出现过 867 秒卡死 |
| 读图 | ✅ 当前消息带图（≤2 张，http 直传 / 本地转 base64） | `_image_refs()` |
| 安全核查 | ✅ 被 @ 可聊、无人叫绝不开口 | followup 已关、无真发送 |

## 2. 待办（按优先级）

| 优先级 | 任务 | 说明 |
|---|---|---|
| **P0** | **双机器人防护** | 群里若另有一个会接话的 bot → 互相触发无限刷屏。必须检测对方是否机器人 |
| **P0** | **实时转发展开** | 影子插件挂的是实时事件，此刻 `Forward` 组件仍在 → 当场 `get_forward_msg` 展开并记录（历史库已丢失 ID，事后无法补） |
| **P1** | **内容提取层** | 统一把非文本变文本：压缩包（zipfile，白名单后缀 + 日志抽 ERROR 行）、链接、语音（core 有 STT）、图片 OCR |
| **P1** | **判定输出扩展** | 除 REPLY/SKIP 外增加：target（针对哪条）、语气、是否引用、是否 @、是否长任务（"我查查，稍后回你"） |
| **P1** | **真发送（半开）** | 先把判定结果私聊推给维护者确认，再放开自动发送；单群 + 低频 |
| **P2** | 长程记忆接入 | 判定前查 livingmemory 语义召回（库里已有 700+ 条记忆） |
| **P2** | 打磨项 | 话题并行、同问题去重、安静时段、敏感话题不插话、刷屏合并 |

## 3. 自动化测试方案（新对话重点，用户明确要求）

**目标：不依赖真实群流量，自己构造消息自己测。**

### 方案 A（已有，快但绕路）
`.workbuddy/proactive_judge_replay.py` —— 直接调判定模型，绕过插件链路。
适合快速迭代 prompt。

### 方案 B（推荐：回放注入，走完整链路）
把 `data_v4.db` 的 `platform_message_history`（2279 条真实语料，覆盖 6 个群）
**重放成合成的群消息事件**，触发插件的 `on_group_message`，让判定、日志、
读图、转发展开全部走真实路径。

要点：
- 需要构造 `AstrMessageEvent` 或复用 core 的事件派发入口
- 合成事件应保留：发送者、时间、消息链（文本/图片/转发/文件）
- 判定结果仍写入 `shadow_log.jsonl`，用 `.workbuddy/shadow_report.py` 统计

### 方案 C（极端场景语料）
手工构造语料，覆盖少见情况：
合并转发、语音、刷屏拆句（一句发 5 条）、话题并行（两条线交叉）、
双机器人互答、撤回、被要求闭嘴、提示注入、凌晨时段、长代码贴。

## 4. 环境事实与已踩的坑（省时间，务必先看）

- **路径**
  - 实例：`C:/Users/philia093/.astrbot_launcher/instances/83ca721d-26d2-4dd0-9932-ef9299d8829d/`
  - 插件：`core/data/plugins/astrbot_plugin_proactive_shadow/`（**不入仓**，属实例数据）
  - 配置：`core/data/config/astrbot_plugin_proactive_shadow_config.json`
  - 日志：`core/data/logs/astrbot.log`；影子日志：插件目录下 `shadow_log.jsonl`
- **插件的坑**（都踩过）
  1. 插件 config **不会自动注入** → 自己读 `data/config/<plugin>_config.json`
     （路径要上两级：`plugins/<name>` → `data/config`）
  2. `message_history_manager.get()` 返回 **PO 对象**，用 `getattr`，不是 `.get()`
  3. 历史的 `user_id` 用**平台实例 id**（`event.get_platform_id()`），不是平台名
  4. `llm_generate` 必须传 `chat_provider_id=`；**不做图片本地化**，本地文件要自己转 base64
  5. provider 的 key 在 `provider_sources[].key`，是 **list**
- **内容可见性边界**（重要，别再猜）
  - 历史库里图片 = `[图片]`、转发 = `[Forward]` 占位，**转发 ID 已丢失**
  - 被引用的转发：core 有引用提取链（`astr_main_agent_quote` → `extractor.py:43`
    → OneBot `get_forward_msg`），被动路径能看到全文
  - 裸发无人引用的转发：被动/主动都看不到（core 级限制）
- **进程纪律**
  - 起机器人前先 `netstat -ano | grep 6185`，有人跑就别再拉
  - **绝不 taskkill 不是自己起的进程**（曾误杀启动器实例）
  - 自己起的要记 PID
- **工具**
  - 测试用 Python：`C:/Users/philia093/.workbuddy/binaries/python/envs/astrbot-test/Scripts/python.exe`
  - ruff：`~/.workbuddy/binaries/python/envs/default/Scripts/ruff.exe`
  - 推送：`GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_workbuddy -o IdentitiesOnly=yes" git push origin maintained/v4.28.2`

## 5. 新对话提示词（直接复制）

```
你接手一个 AstrBot 机器人的「主动回复」项目。先读三份文档再动手，不要凭印象操作：

1. D:/asbot_core_for_fork/docs/maintained/proactive-handoff.md   ← 状态/待办/环境坑
2. D:/asbot_core_for_fork/docs/maintained/proactive-design.md    ← 判定标准（来自真实场景标注）
3. D:/asbot_core_for_fork/docs/maintained/future-ideas.md        ← 背景与机制剖析

你现在要做的事（按顺序，做完一步汇报一步，不要一次做完）：

【第一步 · 自动化回放测试】
目标：不依赖真实群流量，自己构造消息自己测。
- 语料来自 data_v4.db 的 platform_message_history（2279 条真实群聊，覆盖 6 个群）
- 把历史消息重放成**合成的群消息事件**，触发影子插件的 on_group_message，
  让判定、读图、转发展开全部走真实链路（不要只调模型绕路）
- 判定结果仍写 shadow_log.jsonl，用 .workbuddy/shadow_report.py 统计
- 另外手工构造极端场景语料：合并转发、语音、刷屏拆句、话题并行、双机器人互答、
  撤回、被要求闭嘴、提示注入、长代码贴

【第二步 · 补两个 P0】
1. 双机器人防护：检测对方是否机器人，防止两个 bot 互相触发无限刷屏
2. 实时转发展开：在 on_group_message 里，若当前消息含 Forward 组件，
   当场调 get_forward_msg 展开并记录（历史库里转发 ID 已丢，只能当场抓）

【纪律】
- 改动前先说清楚改什么、为什么，必要时先问
- 机器人进程：起之前先查端口；绝不杀不是自己起的进程；自己起的记 PID
- 文档里的「环境事实与坑」必须遵守，那都是踩过的
- 每个改动单独提交，推送到 maintained/v4.28.2
- 汇报时给出具体数字/日志证据，不要只说"已完成"
```

## 6. 自动化回放测试结果（2026-10-21 实跑，532 条判定）

### 怎么跑的

- 工具：`maintained/proactive/replay.py --sample 500`（用法与真假边界见 `maintained/proactive/README.md`）
- 链路：插件自己的 `on_group_message`，配真 `Context` + 真 provider（`ProviderOpenAIResponses`，
  由 core 的工厂逻辑按实例配置造）+ 真 `PlatformMessageHistoryManager`（SQLite）
- 语料：真实群消息 **499 条**（7 个群按大小比例分配）+ 手工极端场景 **33 条**
- 判定模型 `deepseek-v4.1-flash`，用时 644 秒，结果明细 `.workbuddy/proactive_replay_20261021-234608.json`

### 真实语料

| 决策 | 条数 | 占比 |
|---|---|---|
| SKIP | 438 | 88% |
| REPLY | 29 | **5.8%** |
| ERROR | 32 | 6% |

- REPLY 率 5.8%，与线上影子跑出来的 7% 基本吻合 ⇒ **回放可信，可以替代等真实流量**
- 29 条 REPLY 全是实质增量（给排查路径、给具体字段/文件名、给操作步骤），无一条纯情绪
- 32 条 ERROR **全是 25s 超时**；并发降到 2 后重跑 30 条 → 0 超时、41 秒
  ⇒ 是并发打满 provider 限流，不是链路问题；后续固定用 `--concurrency 2`

### 极端场景（33 条，与预期一致 26/33）

| 族 | 条数 | 一致 | 说明 |
|---|---|---|---|
| 合并转发 | 5 | 4/5 | 裸转发/嵌套转发 **根本不进判定**（无纯文本） |
| 语音 | 3 | 2/3 | 语音转文字前判定偏保守 |
| 双机器人 | 5 | 4/5 | 见下，属"碰巧没踩雷" |
| 刷屏拆句 | 3 | 3/3 | 拆句末尾/中间的提问都能接住 |
| 提示注入 | 3 | 3/3 | 三条全 SKIP，理由正确（识别为越狱/劫持） |
| 长代码贴 | 3 | 2/3 | 一条 PARSE_FAIL，**真 bug**，见下 |
| 撤回 / 闭嘴 / 吐槽 / 话题并行 / 基线 | 8 | 8/8 | 全对 |

### 四个偏差的结论

1. **`fwd_quoted_question` 期望 REPLY 实得 SKIP** —— 判定器说"报错指向转发的那段内容，
   图已无法回溯、缺少关键上下文"。**转发内容在主动路径里完全不可见，即便被人引用也不行**
   （历史库只有 `[Forward]` 占位）⇒ 直接坐实 P0「实时转发展开」的必要性。
2. **`voice_with_question` 期望 REPLY 实得 SKIP** —— 语音没转文字时判定器偏保守。
   属内容提取层（P1）前置依赖，不是判定标准的问题。
3. **`bot_helpful_but_wrong` 期望 REPLY 实得 SKIP** —— 模型无从得知"默认 8080"是错的，
   **预期本身不可判定**，非缺陷。
4. **`code_paste_question` 得到 PARSE_FAIL** —— **真 bug**：模型 `draft` 里带真实换行时
   `json.loads` 抛 `Invalid control character`，判定被静默丢弃（表现为"该说的时候没说"）。
   已复现：`json.loads(blob, strict=False)` 可解。长回复场景必踩。

### 双机器人：判定器"碰巧"没踩雷，护不住

5 条里 4 条 SKIP，但理由清一色是"没增量 / 没人提问 / 属可回可不回"，
**没有一条是因为"对方是机器人"**。换个措辞（比如对方接了一句有信息量的话）就会 REPLY，
两个机器人就能互相触发。 ⇒ P0 防护必须做，且不能只靠模型判断。

### 新增可用命令

```bash
# 只看回放记录
python .workbuddy/shadow_report.py --source replay
# 只看某次回放
python .workbuddy/shadow_report.py --run 20261021-234608
# 只看极端场景
python .workbuddy/shadow_report.py --scenarios
```

> 注意：`shadow_log.jsonl` 现在是**线上判定 + 回放判定混在一起**（951 条），
> 回放记录带 `source=replay` / `run_id` / `scenario` 三个标记，用上面的参数筛。

## 7. P0 改动记录（2026-10-22）

### T1 双机器人防护 ✅

改的是实例里的影子插件（不入仓），三层，从硬到软：

| 层 | 判据 | 是否拦截 |
|---|---|---|
| ① 自己 | `sender == event.get_self_id()` | 是 |
| ② 名单 | 配置 `bot_ids`（当前为空，用户说群里基本没机器人）+ 自己的号 | 是 |
| ③ 循环打断 | 最近 N 条只有两个参与者、快速交替、无第三人 | 是 |
| 昵称线索 | 昵称含 机器人/助手/bot/AI | **否，只加权** —— 真人叫"小助手"很常见，直接拦会误伤 |

两个防误伤的设计决定：

- 昵称线索不直接拦截，只把循环窗口从 **6 条缩短到 3 条**
- 无昵称线索时窗口是 **6 条**，因为真人跟机器人快问快答 4-5 条很常见，
  窗口太短会把正常对话误判成互刷（机器人突然不理人，比互刷更糟）

配置项（插件 config，都有默认值）：`bot_ids`（空）、`max_self_talk`=3（最近 6 条里
我方占 3 条就收声）、`loop_max_gap_sec`=45。

**回放验证**（7 条双机器人场景 + 8 条真实语料）：

| 场景 | 结果 | 说明 |
|---|---|---|
| `bot_loop3`（昵称像机器人，来回 6 条） | **被拦** | "疑似双机器人来回（两个号快速交替，无人插话）" |
| `bot_loop_anon`（昵称像真人，来回 8 条） | **被拦** | "最近 6 条里我已占 3 条，收声" |
| `human_rapid_qa`（**真人**跟我快问快答 5 条） | **未误伤** | 走了正常模型判定，防护没介入 ✅ |

最后一条是这次验证最有价值的：防护拦得住互刷，又不会让机器人突然不理真人。
