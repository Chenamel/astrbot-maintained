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

### T2 实时转发展开 ✅

在 `on_group_message` **最前面**（"文本为空就 return"之前）检测 `Forward` 组件，
当场调 `get_forward_msg` 展开，展开文本直接当判定对象。

- 拿 client 的方式：`getattr(event, "bot", None).api.call_action`（getattr 一路兜底，
  非 aiocqhttp 平台自动跳过）。core 的 `OneBotClient` 没从 `astrbot.api` 导出，插件侧只能这样
- 容错：未知 payload 形状（`data` 包裹 / 裸 `messages`）、嵌套转发、非文本段
  （图/文件转 `[image]` 这类占位）都能处理；最多 30 个节点 / 1500 字；全程 try/except
- 落日志：`forward_chars` 字段，能直接看出这次到底展开了多少内容

**回放验证**（给回放事件挂了个假 OneBot client，不用等群里真有人发转发）：

| 场景 | 改前 | 改后 | forward_chars |
|---|---|---|---|
| `fwd_bare`（裸转发） | NO_JUDGE（盲区） | **进判定** | 35 |
| `fwd_nested`（嵌套） | NO_JUDGE（盲区） | **进判定** | 35 |
| `fwd_bare_with_words` | 进判定（但看不到内容） | 进判定（内容可见） | 35 |
| `fwd_quoted_question` | SKIP | SKIP | 0（当前消息本身没转发组件，符合预期） |

判定器现在能看到转发里的原文，例如给出的理由是
"小林已在回答（版本问题），且图片占位无上下文，符合 N1/N2" —— 说明它真的读到了转发内容。

### T3 修 PARSE_FAIL 解析 bug ✅

`json.loads(blob)` → `json.loads(blob, strict=False)`。一行。

根因：模型 `draft` 里带**真实换行**时 json 报 `Invalid control character`，
整个判定被静默丢弃 —— 表现就是"该说的时候没说"，而且长回复必踩（越想说清楚越容易触发）。

验证：`python maintained/proactive/replay.py --selftest`（**不调模型**，确定性）：

```
OK   REPLY       '{"decision":"REPLY","reason":"a","draft":"line1\nline2"}'
OK   SKIP        '```json\n{"decision":"SKIP",...}\n```'
OK   REPLY       '{"decision":"REPLY","reason":"第一行\n第二行","draft":"x"}'
OK   PARSE_FAIL  'not json at all'
=> 4/4 通过
```

第 4 条是防止修过头：真不是 JSON 的时候仍然要判失败，不能什么都吞。

### T3b 解析 bug 还有第二处（回归跑出来的）✅

T4 回归的 200 条真实语料里还剩 1 条 PARSE_FAIL —— 跟换行无关，是**模型多吐了一个右花括号**：

```
{"decision":"REPLY","reason":"...","draft":"哪个游戏哪个角色？"}}   ← 结尾多一个 }
```

`json.loads` 报 extra data，判定照样被丢。改用 `json.JSONDecoder(strict=False).raw_decode()`，
**一次解决两类问题**：控制字符（换行）+ 尾部多余内容。自检加到 5 条，5/5 通过。

### T4 回归验证 ✅

`--sample 200 --concurrency 2` + 全部极端场景，共 235 条，用时 328 秒。

| 指标 | 改前基线 | 改后 | 结论 |
|---|---|---|---|
| REPLY 率 | 5.8% | **6.5%** | 无显著漂移 ✅ |
| ERROR（超时） | 32/499 (6%) | **0** | 并发 2 有效 ✅ |
| 机器人防护拦截 | 无 | **2 条**（`bot_loop3`、`bot_loop_anon`） | 生效 ✅ |
| 转发成功展开 | 0（盲区） | **3 条**（各 35 字） | 生效 ✅ |
| 长代码贴场景 | 2/3 | **3/3** | 解析修复生效 ✅ |

场景整体：35 条里 29 条与预期一致。剩下不一致的集中在
`voice`（语音没转文字，判定偏保守）和 `baseline`/`spam_split` 各 1 条（属判定的边界判断，非缺陷）。

**结论：三项 P0 改动都生效，且没有让原有判定质量退化。**

## 8. 人格来源实测（2026-10-23 晚，重要发现）

### 8.1 self_learning 一直是禁用状态

机器人日志每次启动都写着：

```
Plugin astrbot_plugin_self_learning (4.3.0) ...
Plugin astrbot_plugin_self_learning is disabled.
```

禁用列表存在 `data_v4.db` 的 `preferences` 表（`scope=global`）里：

```
key   = inactivated_plugins
value = ["data.plugins.astrbot_plugin_mcwatcher.main",
         "data.plugins.astrbot_plugin_proactive_chat.main",
         "data.plugins.astrbot_plugin_self_learning.main"]     ← 10-05 起被禁
```

也就是说：我们之前盘点出的「人格主宰 self_learning（命中 6494）」
**从来没参与过**。昨晚那些像人话的 `persona_text`，功劳不在它，而是
**livingmemory（活跃、确实挂在 `on_llm_request` 上）+ PERSONA_PROMPT 的指令**。

### 8.2 即便启用，它的钩子注入默认也是关的

`astrbot_plugin_self_learning_config.json`：

```
Runtime_Internal_Settings: {"enable_llm_hooks": False, ...}
```

所以「启用插件」和「人格真正注入」是**两件事**，都要打开才行。

### 8.3 一个巧合：它内置了 MaiBot 增强

```
MaiBot_Enhancement: {"enable_maibot_features": True,
                     "enable_expression_patterns": True, ...}
```

我们刚调研完的对标物（maibot），功能就内置在这个**已经装着但被禁用**的插件里。
学黑话、表情模式、拟人表达 —— 它可能正好补上我们缺的 L2/L3。

### 8.4 已做的定量验证：对照生成

新增 `persona_control_enabled`（默认关闭）：同一条判定为 REPLY 的消息，
**生成两次** —— 一次走 `on_llm_request` 钩子（方案 A），一次直接用
`Context.llm_generate`（绕过钩子）。两份都落日志（`persona_text` /
`persona_control`），直接对比就能知道钩子到底贡献了多少。

已临时开启。

**实验设计**：两份用**同一个 provider**（`persona_provider_id or provider_id`），
唯一变量是走不走 `on_llm_request` 钩子。
（一开始漏了这个 fallback，对照那份直接拿不到 provider 返回空 —— 已修，
现在两份才真正可比。）

**先做的阴性对照（回放环境，钩子上没有插件挂载）**：

```
【触发】阿星贴了 ModuleNotFoundError 的 Traceback
  走钩子: 先 pip show astrbot 看装没装、装哪了，再确认 main.py 跑的是不是同一个解释器（venv 没激活最常见）。
  不走钩: 先 pip show astrbot 看装没装、装哪了，再确认你运行 main.py 的解释器跟装包的是同一个，虚拟环境没激活的话最容易出这个。
```

两份**语义几乎相同，只是措辞不同** ⇒ 说明两件事：
1. 方法学没有假阳性（不是随便就"看出差异"）
2. 回放环境里钩子确实是空跑 —— 没插件挂上去

于是**真实环境里若出现差异，差异只能来自钩子上的插件（livingmemory 等）**，
这就是我们要测的东西。

**真实环境的样本**（同一模型、同一 prompt，唯一变量是钩子）：

```
【触发】BEAR：哪有低金通解啊
  走钩子: 低金通解本来就是伪命题，硬要说通解也就欢愉队这种能零命叠机制的，
          其他队全是看策划给不给环境，所以别追通解，追你手上拉满的那队就行。
  不走钩: 低金通解真没有，但这版本击破队想压金数就盯着大丽花+阮梅走，生存位带加拉赫，
          主C先用四星顶着，别硬上00全员。

【触发】水鸟乱舞：楼上有个保不住凹了几个小时的
  走钩子: 普通亚婆离确实多数队能稳住，但楼上那位凹几小时大概率是阵容没带对生存位，
          换个有减伤或护盾的辅助，压力立马小一截。
  不走钩: 水鸟那几张是普通亚婆离的截图吧，普通和绝境生存压力差挺多的，
          楼上凹几小时的应该是绝境？        ← 还在追问、不确定

【触发】沐：绝境我20真珠没保住
  走钩子: 20真珠没保住多半是盾量没堆够，绝境那伤害得先看防御位和遗器副词条够不够，
          光靠真珠自己扛不住
  不走钩: 20真珠没保住先看是不是充能没跟上，绝境波次间隔短，真珠大招转不过来就容易断档，
          可以试试换充能绳或者调整出手顺序
```

**差异的方向三条都一样**：

| | 走钩子 | 不走钩 |
|---|---|---|
| 口吻 | 有态度、会吐槽（"本来就是伪命题""看策划给不给环境"） | 中性、书面 |
| 确定性 | 给判断（"大概率是…"） | 爱留问号（"应该是绝境？"） |
| 形态 | 像群里老玩家随口接话 | 像攻略作者写标准答案 |

**结论：`on_llm_request` 钩子确实在贡献，而且贡献的方向正是"像群友"。**
方案 A 从"理论正确"到"实测有效"这条链，到这里才算闭合。

⚠️ 诚实边界：样本只有 3 条，且 LLM 本身有采样随机性，不能排除部分差异来自随机。
但三条**方向完全一致**（走钩子的都更口语、更有态度），趋势是可信的；
样本会继续积累，攒够了再复核一次。

顺带：判定超时 `timeout_sec` 25 → **40**（今天 33 条 ERROR 全是 timeout，
分散在白天各小时，配额不是瓶颈，是 provider 偶发慢）。

### 8.5 待用户决策

**要不要启用 self_learning？** 我的看法：

- 好处：它是现成的人格演化 + 学黑话 + MaiBot 式表达，正是我们缺的
- 风险：它和我们的新插件**同时**往 `on_llm_request` 里注入，可能叠加或冲突
  （这正是"重叠比缺功能更危险"那个警告）
- 建议做法：**先跑完对照实验**，看清钩子现在贡献了多少，再决定要不要加这一路

## 9. 底层排查（2026-10-23 深夜）

用户要求：影子系统"不会真发"这件事不用管，**继续找底层 bug 与扩展对象**。

### 9.1 修掉一个真 bug：`_history` 的 bot id 是硬编码的

```python
"is_bot": getattr(row, "sender_id", "") in {"bot", "3944860270"} or ...
```

而 `_bot_guard` 用的是动态的 `event.get_self_id()` —— **两处对"自己"的认定不一致**。
后果：机器人一换 QQ 号，`_history` 就认不出自己的消息，于是
「我最近说得太多」的计数**静默失效**，循环打断少一条腿。

已改为 `{"bot", "3944860270"} | {self_id}`（self_id 取不到时退回硬编码）。
回放复验：`bot_loop3` 仍被拦、`human_rapid_qa` 未误伤（two_bots 2/2）。

### 9.2 配额确认生效

今天逐小时判定数：**白天几乎每小时都正好卡在 60**（配额上限），说明限流真在兜底。
23 时有 101 条是因为我重启多次（配额是进程内计数，重启重置）—— 正常，非 bug。

⇒ 副产品结论：**白天消息量远超配额**，所以时段配额规则值得配
（如白天 80 / 凌晨 20）。功能已实现，等配置。

### 9.3 反查判定误判（没有系统性漏判）

用正则把"像求助"的触发消息捞出来比对：1015 条 SKIP 里有 87 条像求助，
但抽样 6 条**全部判得对**：

| 触发 | SKIP 理由 |
|---|---|
| 为啥18+画师偏要画成大的呢 | 吐槽，缺实质切入点 |
| 在群里调琴呢 | 玩笑延续，没被点名 |
| 这不我硫磺石吗 | 已有群友接话（N1） |
| 刃2？ | 别人正在回答，排队不抢 |
| 会是台风"蔷琵"的云团吗 | 需专业观测数据，给不了增量 |

⇒ 正则太宽（把吐槽/玩笑也算求助），判定器**没有系统性漏判**。

### 9.4 红线：纯情绪 0 条

80 条 REPLY 里，正则初筛命中 1 条，点开是**误报**：

> 6+1狼配阿哈挺顺的，欢愉主的增益跟6命比稀释得厉害，踹了换阿哈补暴击更值…

是游戏术语「6+1」（6命+1精），不是网络用语「6+」。**实际红线 0 违规**。

### 9.5 待扩展对象（下阶段 S9-6 的输入）

| 对象 | 证据 | 说明 |
|---|---|---|
| **引用（Reply）** | 80 条 REPLY 里 `needs_quote=True` **30 条（37.5%）** | 判定器已经说了该引用，**发送端完全没实现** |
| `is_long_task` | 80 条里 **0 条**为 True | 要么 prompt 定义不清、要么确实没场景，需观察或澄清 |
| 时段/群配额 | 白天每小时打满 60 | 功能已在，只差配置 |
| 形态层（碎片/错字） | 未开始 | 必须先确认 splitter 会不会重复分段 |

## 10. S9-6 第 1 项：引用（Reply）已就绪

数据依据：80 条真实 REPLY 里 **37.5% 判定需要引用**，但发送端此前完全没实现。

### 10.1 一个绕不开的前置问题：历史库没有 message_id

```
platform_message_history 字段: id, platform_id, user_id, sender_id,
                              sender_name, content, llm_checkpoint_id
```

**没有任何平台消息 id** ⇒ 想引用"上一条"，光查库是做不到的。
所以插件必须**自己记 id**：`_recent_ids`（每群一个 deque，上限 `quote_history`，默认 20）。

⚠️ 关键细节：记 id 必须放在**任何 return 之前**。配额和冷却会跳过消息，
如果在判定之后才记，`#1 / #2` 的编号就会和群里实际看到的错位 —— 引用就会引错人。

### 10.2 做法

1. prompt 里给背景**从新到旧编号**（`#1` 是最新，也就是判定对象）
2. 判定器输出 `quote_n`（1 = 引用 #1，0 = 不引用）
3. `_quote_id()` 把编号换算成真实 message_id（越界或重启后为空则降级为不引用）
4. 日志新增 `quote_id` 字段

### 10.3 验证（回放，已改用可区分的 message_id）

```
quote_n=1  quote_id='12471'        ← 真实历史行 id
quote_n=1  quote_id='90000001-3'   ← 场景第 3 条
```

编号与 id 对齐正确。

⚠️ 边界：目前**只在日志里落地**，真正组装 `Reply` 组件要等 S9-7 真发送时接上；
且 `#1` 就是当前消息是最常见情况，引用更早消息依赖 `_recent_ids`（重启即清空）。

## 11. S9-6 第 2 项：消息过滤已实现（默认关闭）

MaiBot 有 `ban_words` / `ban_msgs_regex`，我们此前完全没有 —— 垃圾消息也照样送进判定，白花钱。

**做法**：`_banned(text)` 放在**读历史、调模型之前**，命中就直接 return
（连历史数据库都不读，刷屏时零成本）。

配置（默认空，即不改变任何现有行为）：

```jsonc
"ban_words": ["抽奖", "广告"],      // 含这些词直接跳过
"ban_regex": ["^\d+$"]              // 正则，如纯数字刷屏
```

无效正则会在启动时警告并忽略，**不会**让插件加载失败。

**自检 5/5 通过**：

```
OK  '群里抽奖了快来'   命中=真  命中屏蔽词：抽奖
OK  '12345'          命中=真  命中屏蔽规则：^\d+$
OK  '这是个广告'       命中=真  命中屏蔽词：广告
OK  '帮我看看这个报错'  命中=假
OK  ''               命中=假
```

⚠️ 验证用的屏蔽词**已恢复为空**：我不能替你决定"广告"在你的群里是不是正常词
（比如真有人讨论广告投放）。需要的话自己加，功能已就绪。

## 12. 真机暴露的 bug：生成内容里混进了控制标签（已修）

重启后第一条真实数据就露馅了：

```
说了: <quote id="-995144350"/>难受在追击不稳定吧，被怪先手那回合亏麻…
```

### 12.1 根因

`astrbot_plugin_astrbot_enhance_mode` 在 **`on_llm_request`** 里注入了指令，
要求模型用控制标签表达引用和 @：

```
When you want to quote/reply to a specific message, place <quote id="msg_id"/> …
When you want to mention/@ a user in your reply, use a control tag: <mention id="user_id"/>.
```

它自己在 `on_llm_response` 里把这些标签解析成真正的组件。
**我们的生成不走 `on_llm_response`**（只调 provider），所以标签没人解析，
原样留在文本里 —— 真发送的话，群友会看到一串 XML。

⇒ 这同时也**反过来证明了钩子确实在工作**：enhance_mode 的注入确实生效了。

### 12.2 修法

生成后清理控制标签，但**不丢掉里面的 id**：

- `CONTROL_TAG_RE` 剥掉 `quote / mention / refuse / at / reply` 标签
- `QUOTE_TAG_RE` 把模型给的 id 留下来，记到日志 `quote_id_tag`，
  用于和我们自己算的 `quote_id` 对照（模型可能知道更准的引用目标，也可能幻觉）

自检 4/4 通过。

### 12.3 顺带发现：enhance_mode 本身就有主动回复机制

它的测试文件名暴露了这一点：

```
tests/test_active_judge_policy.py
tests/test_active_reply_context.py
tests/test_followup_delivery.py
```

即**引用 + 主动回复的协议，生态里已经有一套现成的**。

我们的影子插件和它**不冲突**（它是真发送，我们只判定不发送），
但将来 S9-7 真发送时，有两条路：

1. 用我们自己的 `quote_id` 组装 `Reply` 组件
2. **直接沿用 enhance_mode 的标签协议**，让它去解析

第 2 条更省事，也少一层重复。**留到 S9-7 再决定**，现在不预先选。

## 13. S9-7：真发送已开启（2026-10-25，用户批准）

**群 1105248343，全时段。** 至此影子模式结束 —— 从 10-20 起累计约 5200 条判定，
第一次真正开口。

### 13.1 安全设计：默认只对一个群生效

新增 `live_groups`（默认空）：

- **只有列在里面的群会真发**，其余群一律继续只记录不发送
   ⇒ 不会因为配错就把所有群都打开
- 值为字符串时也兼容（WebUI 可能存成"逗号分隔"的文本），按 `[,\s]+` 切分
- 发送走 `Context.send_message` ⇒ **分段和引用都交给 splitter**（见 §11/§7.0，不重复做）
- 发送失败只记日志，不影响判定循环

`mode` 保留为 `shadow`（语义上"以 live_groups 为准"）。

### 13.2 随真发送一起调整的两项

| 项 | 改为 | 理由 |
|---|---|---|
| `willingness_enabled` | **开** | 真发送必须防连发：连着说两句既不像人，也打扰人 |
| `persona_control_enabled` | 关 | 对照实验已得出结论（§8.4），继续开着只是让开销翻倍 |

两项都可在 WebUI 里随时改回来。

### 13.3 WebUI 入口

新增 `_conf_schema.json`，配置项现在能在 **WebUI → 插件 → 本插件 → 配置** 里
直接点选/填写，不用再手写 JSON。覆盖：真发送群、意愿值开关、屏蔽词、每小时上限、
对照开关、判定/人格模型、间隔、超时等。

> 注：AstrBot 自带的"主动回复"总开关在 WebUI 里也有入口，但那属于铁律 6 的范畴
> （`proactive_must_remain_disabled` 恒 true），**与本次开启的不是同一个东西** ——
> 我们走的是插件自己的 `live_groups`。

## 14. 影子系统的载体与环境盘点（2026-10-25）

用户问："影子系统到底是什么载体？有没有过程产物？"

### 14.1 载体构成

| 组成 | 位置 | 是否入仓 |
|---|---|---|
| 插件本体 | `<实例>/core/data/plugins/astrbot_plugin_proactive_shadow/main.py` | ❌ 实例侧，不入仓 |
| 配置 | 同上目录的 `astrbot_plugin_proactive_shadow_config.json` | ❌ |
| 配置 schema | `_conf_schema.json`（WebUI 用） | ❌ |
| 判定日志 | `shadow_log.jsonl`（**约 8MB**） | ❌ **重要数据** |
| 回放/验证工具 | 仓库 `maintained/proactive/{replay,scenarios,report}.py` | ✅ 入仓 |
| fork 底层能力 | `astrbot/core/proactive_persona.py` + `astrbot/api/proactive/` | ✅ 入仓，已进台账 |

即：**影子系统 = 一个实例内的插件 + 一套仓库里的回放验证工具**。
插件本体刻意不入仓（含实例专属配置），入仓的是可复用的工具与底层能力。

### 14.2 清理

- ✅ 已删 `/d/proactive_tmp`（66MB，回放临时数据库与输出，我创建的）
- ✅ `/d/wt_check`（临时工作树）早已清理
- ✅ 仓库工作区干净：`git status` 0 个未跟踪文件
- ⏸ **保留** `/d/pytest_tmp`：pytest 需要它，删了会被沙箱拦截（既有约定）
- ⏸ **保留** `shadow_log.jsonl`：约 5000 条真实判定，是全部结论的依据
- ❓ **待用户确认**：`main.py.bak-20261022-0050`（13KB，10-22 的备份）。
  当前代码已提交且运行正常，删它无风险 —— 但在实例目录下，**未擅自删除**

### 14.3 一个建议：给判定日志加轮转

`shadow_log.jsonl` 目前 ~8MB，按每天数 MB 增长，几个月后会到百 MB 级。
建议加"按大小归档"（如超过 50MB 就改名加时间戳并新建），**未实施**，
等真发送跑一段时间确认格式稳定后再做。
