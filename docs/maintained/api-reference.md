# API 参考 · `astrbot/api/**`

给插件作者看的调用手册。要读设计理由和降级机制，看 [`api-contract.md`](./api-contract.md)；
这里只讲怎么调、传什么、拿回什么、哪里会踩坑。

> 关于旧版本表述的说明
>
> 本文档与 README 曾把这个 fork 描述为"给插件作者留了后门的 AstrBot"。
> 该说法自 `v4.29.4+mtn1` 首个公开版起使用，现统一改为"接口"。
>
> 如果你看的是 GitHub 网页、镜像站（如各类加速代理、`raw` 镜像、第三方镜像站）
> 或搜索引擎快照里缓存的版本，可能仍显示"后门"。那是旧表述，不代表本项目立场：
> 这些模块是公开、有文档、可审查的 Python 接口，不是绕过鉴权的隐蔽入口。
>
> 判断版本新旧的依据：`astrbot/api/**` 的源码、本文件、以及 `maintained/installed_manifest.json`
> 中 10 条 api 文件的 SHA-256。只要文档里出现"后门"作为正式表述，那份就是旧的。

---

## 模块速览

八个模块各管一件事，按你手上的问题挑一个看：

| 你想解决 | 看这个 | 一句话 |
|---|---|---|
| 这条消息是不是已被新一轮取代 | [`api.turns`](#apiturns--回合状态) | 回合状态、合并后的原文与图片 |
| 主动开口时想带上人格和记忆 | [`api.proactive`](#apiproactive--主动回复) | 过 `on_llm_request` 的生成入口 |
| 该发文字还是发文件 / 代码给全了吗 | [`api.delivery`](#apidelivery--交付策略) | 交付策略判定 |
| 这次操作到底有没有被授权 | [`api.permissions`](#apipermissions--执行授权) | 区分"是管理员"与"本次被授权" |
| 模型这次能不能看图 | [`api.media`](#apimedia--视觉输入) | 视觉输入可用性 |
| 这段内容是文字还是图 | [`api.content`](#apicontent--消息段判定) | 消息段类型判定 |
| 时间、路径、下载、钩子时序 | [`api.runtime`](#apiruntime--运行时杂项) | 运行时杂项 |
| 这个对象是不是 embedding provider | [`api.embedding`](#apiembedding--向量化) | 向量化判定 |

---

## 读之前

每个模块都有 `available()`。 在上游原版 AstrBot 上调用会返回 `False`，
这时该模块的其他函数要么返回安全默认值、要么抛异常（下面逐个标注）。
写插件时先判断，同一份代码就能在官方版和本 fork 上都能跑：

```python
from astrbot.api import turns

if turns.available():
    text = turns.merged_text(event)
else:
    text = event.message_str        # 官方版退化路径
```

`resolve()` 不用管。 每个模块都导出它，那是内部桥接用的，插件不应该调。

---

## `api.turns` —— 回合状态

一轮对话可能由多条消息拼成（消息聚合）。这个模块回答"我现在处理的是哪一轮、原文是什么"。

### `available()` · turns

回合状态支持是否就位。上游原版返回 `False`。

### `is_current(event) -> bool`

这条事件还算不算当前回合。

参数：`event`：`AstrMessageEvent`
返回：`True` 表示还能继续投递

**注意**：失败时放行。检查本身出错或能力缺失时返回 `True`，宁可不拦，也不能把用户的回复悄悄吞掉。所以它不能用来做"这条过时了"的严格断言。

```python
if turns.is_current(event):
    await event.send(...)      # 还可以发
```

### `merged_text(event) -> str`

这一轮合并后的完整文字。

返回：合并文本；没有则空字符串。不会返回 `None`，可以直接拼字符串。

```python
text = turns.merged_text(event)     # "帮我看下这个"+"顺便修一下" → 合并结果
```

### `merged_image_urls(event) -> list[str]`

这一轮合并后的图片 URL 列表。

返回：URL 列表；没有则空列表（不是 `None`）。

### `turn_version(event) -> int | None`

这条事件携带的回合版本号。

返回：版本号；事件没有回合信息时返回 `None`。

用途：同一轮里多次生成时，用它判断是不是同一版回合，避免把旧结果当新的。

### `mark_sent(event) -> None`

标记这一轮的回复已经发出。

参数：`event`：完成投递的事件
返回：无

**注意**：只在确实发出去之后调。提前调用会让系统以为已经回过，后续判断出错。

### `reset(unified_msg_origin) -> bool` / `reset_all() -> bool`

清掉一个会话 / 全部会话的回合状态。

返回：`True` 表示确实清掉了

**注意**：这是本模块仅有的两个改状态的函数。`api-contract.md` 的整体约束是"只读转发"，这两个是明确的例外，别在正常流程里随手调。

---

## `api.proactive` —— 主动回复

官方 `Context.llm_generate` 直接调 provider，跳过 `on_llm_request` 钩子：
所以人格插件、记忆插件对它生成的内容完全不生效，主动开口常常"不像本人"。
本模块让生成先过一遍钩子。

### `available()` · proactive

主动能力是否就位。

### `persona_available() -> bool`

能走人格链的生成器是否装好了。注意它不接受参数。

`available()` 为 `True` 不代表 `persona_available()` 也为 `True`，两个都要检查。

### `generate_with_persona(context, event, prompt, ...) -> LLMResponse | None`

异步。 走人格链生成一段话。

#### 参数

| 名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `context` | `Context` | ✅ | 插件拿到的 context |
| `event` | `AstrMessageEvent` | ✅ | 触发这次主动回复的事件 |
| `prompt` | `str` | ✅ | 让 bot 说什么 / 对什么作反应 |
| `system_prompt` | `str` | — | 只对本次调用生效的额外指令，默认空 |
| `image_urls` | `list[str]` | — | 随 prompt 一起送的图片 |
| `chat_provider_id` | `str` | — | 指定 provider，默认用当前那个 |
| `timeout` | `float` | — | 本次调用的秒级超时 |

返回：`LLMResponse`；以下情况返回 `None`：能力缺失、没有可用 provider、或被某个插件在钩子里取消了请求。

#### 注意

- 返回 `None` 不等于出错。可能只是有人（别的插件）决定这次不该说，调用方应当安静跳过，不要重试、不要报错。
- 它比 `llm_generate` 多跑一遍钩子链，所以更慢。一次主动回复只调一次，不要在循环里调。

```python
from astrbot.api import proactive

if proactive.available() and proactive.persona_available():
    resp = await proactive.generate_with_persona(
        context, event, "群里刚才聊到的那事，接一句",
        timeout=30,
    )
    if resp is not None:
        await event.send(resp)
else:
    resp = await context.llm_generate(prompt="...", contexts=[])   # 官方版路径
```

### `proactive_switch_is_disabled() -> bool`

恒返回 `True`。

这是本 fork 的硬约束：主动回复在代码层面无法被打开，
记录在 `maintained/installed_manifest.json` 的 `proactive_must_remain_disabled` 字段里。

**注意**：看到它别当成"开关状态查询"，它是不变量声明。想集成主动回复的插件，
这个函数返回 `True` 意味着"本 fork 不会替你做主动触发"，你得自己管时机。

### `is_lightweight_proactive(event) -> bool`

core 是否把这次请求判定为"轻量主动"。

**注意**：失败时收紧：判定器不可用时返回 `False`，让请求走完整的常规路径。
和 `is_current` 的"失败放行"正好相反，这里是故意的：拿不准就走稳妥那条。

### `record_bot_message(context, event, text) -> bool` / `record_user_message(context, event, text, max_messages=700) -> bool`

异步。 把一条消息写回平台历史。

返回：`True` 表示这条确实在历史里了；`False` 表示没写进去，调用方应当在意。

#### 注意

- 机器人只读群里的发言、不读自己说过的话，就会忘记已经说过什么。所以主动回复**发出后必须写回**，否则下一轮它不知道这句话存在。
- `record_user_message` 的 `True` 有两种来源：我们写进去的，或 core 早就记过了。都算成功。
- `max_messages` 是每个会话保留的行数上限，超出丢最旧的，默认 700。
- `context` 参数目前没用上，保留只是为了和同类函数签名一致。

---

## `api.delivery` —— 交付策略

该发文字还是发文件？模型这段回复算不算真的给了代码？

### `available()` · delivery

### `has_code_delivery(text, language="") -> bool`

模型回复里是否真的带了一段完整代码。

参数：`text` 回复正文；`language` 期望语言，空串表示自动推断
返回：`True` 当且仅当存在真实、未被省略的代码块

**注意**：`...`、`# 略`、`此处省略` 这类占位不算交付。用它判断"到底给没给完整代码"，
比自己在正文里数反引号可靠。

```python
if not delivery.has_code_delivery(reply, "python"):
    await event.send("代码没给全，我再补一次")
```

### `code_task_spec(event) -> tuple[str, str] | None`

这个事件是否在要求写代码。

返回：`(text, language)` 二元组；不是代码任务则 `None`

---

## `api.permissions` —— 执行授权

区分"这个人是管理员"和"这一次操作被授权了"。官方只给前者。

### `available()` · permissions

### `is_admin(event, config) -> bool`

发送者是否在管理员名单里。

参数：`config` 是 AstrBot 的配置映射（里面读 `admins_id`）

### `execution_denial(event, config) -> str | None`

这次执行类操作**是否必须拒绝**。

返回：必须拒绝时给一句可以直接展示给人看的理由；否则 `None`

#### 注意

- 返回的是给用户看的文字，可以直接 `await event.send(reason)`。
- 它和 `is_admin` 是**两件事**：管理员身份通过，也可能因为"本次消息没明确要求执行"被拒。
  本 fork 的 `execution_gate_mode` 设成 `strict` 时，后者的判定会更严。

> [!IMPORTANT]
> **`None` 才是放行，不是 `False`。**
> 别写成 `if not execution_denial(...)` 就放行，那样 `""` 之类的空值也会被当成"已拒绝"，
> 反之一个假值也可能被误读。判断一律用 `is not None`。

```python
reason = permissions.execution_denial(event, context.get_config())
if reason is not None:
    await event.send(reason)
    return
run_the_command()
```

---

## `api.media` —— 视觉输入

模型这次到底能不能"看见"图。

### `available()` · media

### `has_visual_input(request) -> bool`

请求里是否带着真实的视觉证据（图片 URL 或 image content part）。

**参数**：`request`：`ProviderRequest` 一类的对象

### `image_input_available(request) -> bool`

这次请求的视觉输入**是否可用**。

**注意**：优先信 core 维护的标志位；标志位缺失时，退化成"请求里到底有没有视觉输入"。
比 `has_visual_input` 更贴近"模型能不能依赖这张图"，能用这个就别用那个。

### `has_image_caption(parts) -> bool`

任何一段内容里是否带了图片说明文字。

**参数**：`parts`：可迭代的内容段，**对象或 OpenAI 风格 dict 都接受**

**注意**：判断的是有没有 `IMAGE_CAPTION_MARKER` 标记，不是"图片有没有配文字"这种语意判断。

---

## `api.content` —— 消息段判定

### `available()` · content

### `is_text_part(part) -> bool`

### `is_image_part(part) -> bool`

**参数**：内容段，**两种形式都接受**：core 的 content part 对象，或 OpenAI 风格的
`{"type": "image_url"}` dict。调用方不用关心请求里用的是哪种。

**注意**：`is_text_part` 要求 core 类型**已就位**才可能返回 `True`；
`is_image_part` 对 dict 形式也认。跨版本兼容时优先用 `is_image_part`。

---

## `api.runtime` —— 运行时杂项

### `available()` · runtime

### `get_astrbot_data_path() -> str`

数据目录的绝对路径。

**注意**：core 版助手不可用时回退到 `<当前目录>/data`，这样插件在未打补丁的 core 上仍能加载。
所以**别假设这个路径一定等于实例的数据目录**，只在"能读写就行"的场景用它。

### `format_local_time(value, with_seconds=True, with_date=True) -> str`

把存下来的时间戳渲染成本地时间。

**参数**：`value` 可以是 `datetime`（**naive 值按 UTC 处理**）、ISO-8601 字符串，或秒级时间戳

**注意（这条最容易错）**：数据库里存的是 **naive UTC**，而日志、用户、系统提示词说的都是本地时间。
插件把库里的时间直接 `str()` 塞进文本，一次提示里就会出现两个时区。
**凡是要给人或模型读的时间，都必须过这个函数。**

```python
from astrbot.api import runtime
ts = row["created_at"]                  # naive UTC
await event.send(f"上次说话是 {runtime.format_local_time(ts)}")
```

### `hook_timing_mode(event=None) -> str`

当前回合的完成钩子时序，返回 `"enhanced"` 或 `"legacy"`。

- `"enhanced"`：完成钩子**在回复发出之前**触发，可以在发出前拦截改写
- `"legacy"`：恢复上游时序，回复先发、钩子后触发

**注意**：依赖"回复已经发出去了"这个前提的插件，必须先查这个值。
拿到 `"legacy"` 就走保守路径，或直接告诉用户。**把 `event` 传进去**更准，
不传的话返回的是进程里最后一次构建的模式，处理并发请求时可能对不上。

### `extract_quoted_message_images(event, component) -> list[Any]`

取出被引用消息里的图片。

**返回**：图片引用列表；core 助手不可用时返回**空列表**（等价于"这条引用没有图"）

**注意**：空列表可能是"真没有图"，也可能是"能力不在"。要区分就得先查 `available()`。

### `download_image_by_url(url, *args, **kwargs) -> Any`

**异步。** 通过 core 助手下载图片，返回它的返回值（通常是本地文件路径）。

> [!WARNING]
> **这是本套 API 里唯一会抛异常的降级点。**
> core 助手不可用时它直接抛 `RuntimeError`，而不是像旁边的函数那样返回 `None`。
> 这是故意的，下载失败悄悄返回空值，后面会变成一个更难查的 `NoneType` 错误。
> **调用处必须 try。**

```python
try:
    path = await runtime.download_image_by_url(url)
except RuntimeError:
    logger.warning("下载不可用，跳过这张图")
```

---

## `api.embedding` —— 向量化

### `available()` · embedding

### `is_embedding_provider(candidate) -> bool`

`candidate` 是不是一个 embedding provider。

**注意**：core 类型不可用时返回 `False`："判断不了"和"不是"在这里不区分。

---

## 速查：出错时会怎样

| 函数 | 能力缺失时 |
|---|---|
| `is_current` | 返回 `True`（放行） |
| `is_lightweight_proactive` | 返回 `False`（走常规路径） |
| `merged_text` / `merged_image_urls` | 空字符串 / 空列表 |
| `execution_denial` | 返回 `None`，但**不代表安全**——先查 `available()` |
| `extract_quoted_message_images` | 空列表 |
| `download_image_by_url` | **抛 `RuntimeError`** |
| 各 `is_*_part` / `is_embedding_provider` | 返回 `False` |
| `generate_with_persona` | 返回 `None` |

**共同前提**：这些默认值只保证"不会崩"，不保证"语义正确"。
真正需要正确判断的地方，一律先 `available()`。

---

## 相关文档

- [`api-contract.md`](./api-contract.md)：设计约束与降级契约（规格来源）
- [`plugin-quickstart.md`](./plugin-quickstart.md)：5 分钟入门
- [`design.md`](./design.md)：为什么这样分层
