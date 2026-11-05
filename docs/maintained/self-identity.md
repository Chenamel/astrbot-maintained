# 自我身份不变式（R2）

## 一、问题（有实证）

2026-11-02 11:58，群 <group-id>，机器人在主动回复里说出：

> 那条是权限插件拦下来时自己发的回执，不是消息内容本身……

而那条「管理命令仅管理员可用。」是某位用户发出的（更准确地说：是 QQ 桥在拦截命令时追加的文本，
该用户本人在 15 秒后亲自解释了）。判定器的 `reason` 里并没有这句话，它是人格生成阶段
自己补出来的出生。

结构性原因：模型拿到的请求里，没有任何一处说明哪个账号是它自己。

- `_append_system_reminders` 只注入了用户身份（`User ID: …, Nickname: …`）；
- 主动生成的 `generate_with_persona` 根本不经过这个函数；
- 历史渲染里，自身标记有三种写法（`BOT` / `机器人` / `[You/…]`），且不是每条链路都有。

## 二、决议：一条不变式，两处注入

新增 `astrbot/core/utils/self_identity.py::self_identity_note(event)`，返回一段说明：

- 你的账号是 `{self_id}`；
- 群聊里只有标 `BOT` / `机器人` / `[You]` 的行是你说过的话；
- 挂在其他昵称下的行不属于你；
- 在自己的记录里找不到某句话时，不许声称那是你说的。

调用点只有两个，文本只定义一次：

| 路径 | 位置 |
|---|---|
| 普通回复 | `astr_main_agent._append_system_reminders`（排在用户身份之前） |
| 主动生成 | `proactive_persona.generate_with_persona`（在跑 `on_llm_request` 之前写入 `system_prompt`） |

## 三、边界（明确不做）

- **不硬编码机器人昵称**：昵称来自人格配置，核心只保证账号准确。
- **不改上游既有行**：`User ID/Nickname`、`Group name`、`Current datetime` 原样保留。
- **不覆盖第三方渲染**：第三方若自行渲染「机器人账号」「代词映射」，行为照旧；本不变式是兜底，不是替代。
- **暂不改判定器提示词**：判定器不写话；改它的措辞会改变判定分布，需要 replay 单独验证。

## 四、验收

1. `tests/maintained/test_self_identity.py`：群聊含账号与归属规则、私聊只含账号、`self_id` 为空时不注入、
   `_append_system_reminders` 与 `generate_with_persona` 两条路径都带上。
2. 抓包（`_llm_capture`）：主动生成请求的 `system_prompt` 里出现该行。
3. 既有 603 项 maintained 测试不减少。
