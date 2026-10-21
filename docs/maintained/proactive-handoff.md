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
