# 合并转发展开（main agent）

> 登记项：`astrbot/core/utils/forward_expand.py`（新增）、
> `astrbot/core/astr_main_agent.py`（注入点）
> 关联提交：`feat(agent): expand merged forwards before the agent sees them`

## 问题

一条合并转发到达框架时，`Forward` 组件（`astrbot/core/message/components.py`）
**只有一个 `id`，不含任何内容**。消息归档里也只留下 `[Forward]` 占位符。

结果是：群里有人发一条转发（搬运聊天记录、长图集），**主对话只能看到一个占位符**，
既读不到正文也看不到图，回复自然答非所问。

判定器插件（`astrbot_plugin_proactive_shadow`）此前自己实现了展开，注释写得很直白：
"the archive only keeps a `[Forward]` placeholder, so a later look at history can never
recover the content -- **this event is the only chance**"。主对话缺的正是这一步。

## 改动

新增 `astrbot/core/utils/forward_expand.py`：

- `expand_forward_text(event, max_chars=1500) -> str`
- 从 `event.get_messages()` 取 `Forward` 组件
- 通过 `event.bot.api.call_action("get_forward_msg", id=...)` 取内容
  （OneBot 风格适配器；其他平台没有 `call_action` 时直接返回空）
- 渲染为 `昵称：正文` 行；非文本段降级为 `[image]`/`[file]`/`[video]`/`[record]` 标记
- **失败永不抛出**：适配器报错、payload 形状不认识、超时（10s）一律返回空串

在 `astr_main_agent.py` 的 `_decorate_llm_request()` 中注入（`_apply_prompt_prefix` 之后）：

```python
forwarded_text = await expand_forward_text(event)
if forwarded_text:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Forwarded conversation]\n{forwarded_text}")
    )
```

复用既有的 `extra_user_content_parts` 机制，与引用附件、系统提醒同一条通道。

## 边界（有意为之）

| 边界 | 值 | 理由 |
|---|---|---|
| 只展开**当前消息**的转发 | — | 历史里的转发早已拿不到内容，且重复展开会让 token 爆炸 |
| 字符上限 | `FORWARD_MAX_CHARS = 1500` | 转发可以任意大，必须设上限 |
| 节点上限 | `FORWARD_MAX_NODES = 30` | 超长转发只取前 30 条 |
| 单次调用超时 | 10s | 适配器无响应不能拖住回复 |
| 失败行为 | 返回空串，请求照旧 | 看不到转发≠不能回复 |

## 兼容性

- **无 `Forward` 组件时零开销**：立刻返回空串，不触达适配器（有测试覆盖）。
- 适配器不提供 `call_action`（如 WebChat）时返回空串，行为与改动前一致。
- 上游测试全量通过（见提交记录）；维护侧新增 8 项测试覆盖
  "渲染 / 无转发不调用 / 无 API 返回空 / 异常吞掉 / 未知形状 / 截断 / 非文本标记 / 上限合理"。

## 与判定器插件的关系

插件里那份 `_expand_forward` 与本次 core 实现逻辑一致（同样的 id 取内容 + 字符上限）。
后续可以把插件改为调用 `astrbot.core.utils.forward_expand`，避免两份实现漂移；
本次**未动插件**，因为改动应先落在 core、插件保持可用。

## 配套的配置调整

同一轮把 `provider_settings.max_quoted_fallback_images` 从 **20 降到 6**
（引用消息回填图片上限）。依据：引用合并转发走的正是这条 fallback 路径
（代码注释点名 `[Forward Message]` 占位符场景），20 张图约 3 万 token，
而实测主对话出现过 49,515 的单次输入，与其吻合。

降到 6 而非 3：转发场景下文本此前进不来、图是唯一信息源，砍太狠会"看不懂"。

## 台账

`maintained/installed_manifest.json` 共 **53 条**；本次新增
`astrbot/core/utils/forward_expand.py`（`astr_main_agent.py` 原已登记，同步哈希）。
