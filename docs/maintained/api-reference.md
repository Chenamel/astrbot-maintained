# API 参考 · `astrbot/api/**`

面向插件作者的接口调用手册。设计约束与降级规格见 [`api-contract.md`](./api-contract.md)；本文说明各模块函数的参数、返回值与调用边界。

> 关于旧版本表述的说明
>
> 本文档与 README 在早期公开版本（形如 `v4.29.4+mtn1`）中曾将本层扩展描述为"给插件作者留了后门的 AstrBot"，现已统一改为"接口"。
>
> 若在第三方镜像站、加速代理或搜索引擎快照中看到"后门"字样，均为历史缓存。这些模块是公开、有文档、可逐行审查的 Python 接口，不包含任何绕过鉴权的隐蔽入口。
>
> 校验版本新旧可核对 `astrbot/api/**` 源码、本文件以及 `maintained/installed_manifest.json` 中的 SHA-256。

## 模块速览

| 场景需求 | 对应模块 | 核心职责 |
|---|---|---|
| 判断当前消息是否已被新一轮发言取代 | [`api.turns`](#apiturns--回合状态) | 回合状态、合并后的原文与图片 |
| 主动发言时带上人格、记忆与群上下文 | [`api.proactive`](#apiproactive--主动回复) | 经过 `on_llm_request` 钩子的生成入口与历史写回 |
| 判断模型回复是否包含完整代码 | [`api.delivery`](#apidelivery--交付策略) | 代码任务识别与交付完整性判定 |
| 区分管理员身份与单次执行意图授权 | [`api.permissions`](#apipermissions--执行授权) | 管理员判定与执行授权检查 |
| 判断当前请求是否具备可用图片输入 | [`api.media`](#apimedia--视觉输入) | 视觉输入可用性与图片说明检测 |
| 判断消息内容段是文本还是图片 | [`api.content`](#apicontent--消息段判定) | 消息内容段类型判定 |
| 获取数据目录、本地时间、下载图片、查询钩子时序 | [`api.runtime`](#apiruntime--运行时杂项) | 运行时辅助工具 |
| 判断对象是否为向量化 provider | [`api.embedding`](#apiembedding--向量化) | Embedding provider 类型判定 |
| 安全读写事件附加字段与声明工具能力 | [`api.event.extras`](#apieventextras--事件附加字段与工具能力声明) | 事件附加字段读写器与 `FunctionTool` 能力标记 |

## 调用前提

每个功能模块均提供 `available() -> bool`。在上游原版 AstrBot 上调用时返回 `False`，模块内其余函数会返回安全默认值（仅 `runtime.download_image_by_url` 会显式抛出 `RuntimeError`）。在插件中先判断 `available()`，即可让同一份插件代码同时兼容官方原版与维护分支：

```python
from astrbot.api import turns

if turns.available():
    text = turns.merged_text(event)
else:
    text = event.message_str        # 官方原版退化路径
```

各模块导出的 `resolve()` 为内部桥接辅助函数，插件请勿直接调用。

## `api.turns` —— 回合状态

当同一发送者在静默窗口内连续发送多条消息时，系统会将其合并为一轮对话。本模块用于查询当前事件所属的回合状态与合并内容。

### `available()` · turns

返回回合状态支持是否就位；上游原版返回 `False`。

### `is_current(event) -> bool`

判断该事件是否仍属于当前最新回合。

- 参数：`event`（`AstrMessageEvent`）
- 返回：`True` 表示仍可继续投递回复。
- 注意：采用 fail-open 策略。当检查出错或底层能力缺失时恒返回 `True`，避免静默吞掉正常回复；请勿将其用于「事件必然已过期」的严格反向断言。

```python
if turns.is_current(event):
    await event.send(...)
```

### `merged_text(event) -> str`

获取当前回合合并后的完整文本。无合并文本时返回空字符串 `""`（不返回 `None`）。

```python
text = turns.merged_text(event)
```

### `merged_image_urls(event) -> list[str]`

获取当前回合合并并去重后的图片 URL 列表。无图片时返回空列表 `[]`。

### `turn_version(event) -> int | None`

获取当前事件携带的回合版本号；事件无回合信息时返回 `None`。可用于同一回合内多次异步生成时的版本比对。

### `mark_sent(event) -> None`

标记当前回合已完成回复投递。

- 注意：仅在实际发出回复后调用。提前调用会导致后续流程误判本回合已回复。

### `reset(unified_msg_origin) -> bool` / `reset_all() -> bool`

清空指定会话或全部会话的回合聚合状态，成功清空返回 `True`。

- 注意：会直接清空会话的回合聚合状态，仅用于会话重置或异常恢复，正常消息处理流程中不要调用。

## `api.proactive` —— 主动回复

上游原版的 `Context.llm_generate` 直接调用底层模型 provider，跳过了 `on_llm_request` 钩子，导致人格与记忆插件无法介入。本模块提供经过完整请求钩子链的生成入口与历史写回函数。

### `available()` · proactive

返回轻量主动判定能力是否就位。

### `persona_available() -> bool`

返回人格感知生成能力是否就位（无参数）。注意：`available()` 为 `True` 不代表 `persona_available()` 也为 `True`，调用生成前请检查 `persona_available()`。

### `generate_with_persona(context, event, prompt, ...) -> LLMResponse | None`

异步协程。先执行 `on_llm_request` 钩子链，再调用模型生成回复。

#### 参数

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `context` | `Context` | ✅ | 插件持有的 `Context` 实例 |
| `event` | `AstrMessageEvent` | ✅ | 触发本次主动回复的事件 |
| `prompt` | `str` | ✅ | 本次生成的任务提示词 |
| `system_prompt` | `str` | — | 仅对本次调用生效的附加系统指令，默认 `""` |
| `image_urls` | `list[str]` | — | 随请求附带的图片 URL 列表 |
| `chat_provider_id` | `str` | — | 指定对话 provider ID，默认使用当前会话主模型 |
| `timeout` | `float` | — | 单次调用超时秒数 |

返回：`LLMResponse`；若底层能力缺失、无可用 provider，或请求在钩子链中被其他插件调用 `stop_event()` 取消，则返回 `None`。

#### 注意

- 默认按 `event.unified_msg_origin` 解析会话主模型，复用普通回复的选择规则（会话偏好、会话配置、框架回退）；显式指定 `chat_provider_id` 时只使用指定模型，找不到则返回 `None`，不会改投其他模型。旧 Context 缺少异步选择接口时保留全局模型回退；接口存在但返回空或抛错时，不借此改用全局模型。
- 人格使用当前选中对话的 `persona_id`，交由已有解析器按“会话强制规则 → 对话选择 → 配置默认”处理，保留显式“无人格”。只读既有对话，不创建对话、不导入历史；对话不存在时按无对话选择处理。人格读取或解析异常时沿用告警并跳过本次人格注入的行为。请求钩子仍可后续修改提示词，因此“无人格”仅约束核心人格注入。
- 返回 `None` 可能是被上游防抖或过滤插件主动拦截，调用方应直接跳过发送，不要当作异常报错。
- 每次调用均会完整遍历 `on_llm_request` 钩子链，单次主动回复只应调用一次，切勿在循环中高频调用。

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
    resp = await context.llm_generate(prompt="...", contexts=[])
```

### `proactive_switch_is_disabled() -> bool`

恒返回 `True`。表示 `astrbot/api/proactive/` 仅提供判定标记、人格生成与历史写回原语，不内置主动触发调度器。官方内置的 `provider_ltm_settings.active_reply.enable` 与插件自身的主动开关各自独立，同一实例同一时间只应启用一套。

### `is_lightweight_proactive(event) -> bool`

判断当前请求是否被标记为轻量主动场景。底层能力未就位时返回 `False`（fail-closed，回退至常规完整路径）。

### `record_bot_message(context, event, text) -> bool` / `record_user_message(context, event, text, max_messages=700) -> bool`

异步协程。将机器人刚发出的主动回复或收到的群消息写回平台历史库。

- 返回：`True` 表示该消息当前已存在于历史库中（包含本次新写入或此前已存在）；`False` 表示写入失败或跳过。
- 注意：主动回复发出后必须调用 `record_bot_message` 写回历史，否则机器人在下一轮对话中不会知道自己刚刚说过这句话。`max_messages` 控制单会话保留的最大历史条数，默认 700。

## `api.delivery` —— 交付策略

用于识别用户消息是否在请求编写代码，以及模型回复中是否真正交付了完整代码。

### `available()` · delivery

### `has_code_delivery(text, language="") -> bool`

判断回复文本中是否包含指定语言的完整代码块（自动剔除仅含 `...`、`# 略`、`此处省略` 等占位符的伪代码块）。`language` 为空字符串时自动推断语言。

```python
if not delivery.has_code_delivery(reply, "python"):
    await event.send("代码没给全，我再补一次")
```

### `code_task_spec(event) -> tuple[str, str] | None`

判断事件是否在请求编写代码；若是则返回 `(任务文本, 目标语言)` 二元组，否则返回 `None`。

## `api.permissions` —— 执行授权

区分「发送者是管理员」与「当前这条消息明确授权执行代码或命令」。

### `available()` · permissions

### `is_admin(event, config) -> bool`

判断发送者是否在 `config["admins_id"]` 管理员列表中。不依赖底层补丁，始终可用。

### `execution_denial(event, config) -> str | None`

判断本次执行类操作是否必须拒绝。

- 返回：放行返回 `None`；拒绝时返回可直接展示给用户的拒绝原因字符串。
- 注意：当 `execution_gate_mode` 设为 `strict` 时，即使发送者是管理员，若当前消息未明确包含运行/执行指令（例如仅引用文档或代码块），同样会返回拒绝原因。

> [!IMPORTANT]
> **`None` 才是放行，请使用 `is not None` 判断。**
> 不要写成 `if not execution_denial(...)`，必须显式判断 `if reason is not None:`。

```python
reason = permissions.execution_denial(event, context.get_config())
if reason is not None:
    await event.send(reason)
    return
run_the_command()
```

## `api.media` —— 视觉输入

用于判断当前请求是否携带有效图片输入，以及获取防幻觉常量。

### `available()` · media

### `has_visual_input(request) -> bool`

判断 `ProviderRequest` 对象是否携带视觉输入（非空 `image_urls` 或 `ImageURLPart` / `image_url` 字典）。

### `image_input_available(request) -> bool`

判断当前请求的视觉输入是否可用（综合检查 `not request.image_input_unavailable` 与实际视觉输入）。判断模型能否看图时优先使用本函数。

### `has_image_caption(parts) -> bool`

判断内容段序列中是否包含带 `IMAGE_CAPTION_MARKER`（`"<image_caption>"`）标记的图片转述文本。同时兼容内容段对象与 OpenAI 风格 dict。

## `api.content` —— 消息段判定

### `available()` · content

### `is_text_part(part) -> bool` / `is_image_part(part) -> bool`

判断单个内容段是否为文本段或图片段。同时接受 core 的 `TextPart` / `ImageURLPart` 对象与 OpenAI 风格的 `{"type": "image_url"}` 字典；插件侧请始终使用这两个函数，避免直接调用 `isinstance(part, TextPart)`（当底层类缺失为 `None` 时 `isinstance` 会抛 `TypeError`）。

## `api.runtime` —— 运行时杂项

### `available()` · runtime

### `get_astrbot_data_path() -> str`

返回数据目录的绝对路径；底层助手缺失时回退为 `<当前工作目录>/data`。

### `format_local_time(value, with_seconds=True, with_date=True) -> str`

将存储时间戳转换为本地时间字符串。支持 `datetime`（naive 对象按 UTC 处理）、ISO-8601 字符串或秒级时间戳。

- 注意：数据库中存储的 `created_at` 等字段均为 **naive UTC**，而日志与模型提示词使用本地时间。凡是将存储时间拼入展示文本或提示词的场景，均须经过本函数换算，避免同一段上下文中出现 8 小时时差。

```python
from astrbot.api import runtime
ts = row["created_at"]                  # naive UTC
await event.send(f"上次说话是 {runtime.format_local_time(ts)}")
```

### `hook_timing_mode(event=None) -> str`

查询当前生效的完成钩子时序模式，返回 `"enhanced"`（完成钩子在回复发出前触发）或 `"legacy"`（回复先发出、完成钩子后触发）。建议传入 `event` 以获取当前请求绑定的精确模式。

### `extract_quoted_message_images(event, component) -> list[Any]`

异步协程。提取被引用消息中的图片列表；底层不可用或无引用图时返回空列表 `[]`。

### `download_image_by_url(url, *args, **kwargs) -> Any`

异步协程。调用 core 下载图片并返回本地文件路径。

> [!WARNING]
> **这是扩展 API 中唯一在底层能力缺失时抛出异常的函数。**
> 当底层下载助手不可用时会直接抛出 `RuntimeError`，避免返回 `None` 导致后续文件读取出现难以排查的空指针错误。调用处必须使用 `try...except RuntimeError` 捕获。

```python
try:
    path = await runtime.download_image_by_url(url)
except RuntimeError:
    logger.warning("下载不可用，跳过这张图")
```

## `api.embedding` —— 向量化

### `available()` · embedding

### `is_embedding_provider(candidate) -> bool`

判断 `candidate` 是否为 `EmbeddingProvider` 实例；底层类型缺失时返回 `False`。

## `api.event.extras` —— 事件附加字段与工具能力声明

### 事件附加字段（`astrbot.api.event.extras`）

提供跨模块共享的 9 个事件附加字段键名常量、10 个带类型校验与默认值兜底的读取函数，以及 1 个写入函数（详见 [`api-contract.md`](./api-contract.md) §3.6）：

- 读取器：`active_reply_token(event) -> str`、`is_active_reply(event) -> bool`、`visual_requested(event) -> bool`、`visual_unavailable(event) -> bool`、`owned_image_urls(event) -> list[str]`、`owned_quote_image_urls(event) -> dict[str, list[str]]`、`followup_direct(event) -> bool`、`followup_task(event) -> str`、`proactive_lightweight(event) -> bool`、`active_reply_triggered(event) -> bool`。
- 写入器：`set_visual_unavailable(event, flag: bool) -> None`。

### 工具能力自声明字段（`FunctionTool`）

插件在构造 `FunctionTool` 时可通过以下两个布尔字段（默认均为 `False`）声明工具属性：

| 字段 | 类型与默认值 | 语义 |
|---|---|---|
| `is_execution_tool` | `bool = False` | 声明该工具会执行代码或系统命令，需通过当前消息的 `execution_denial` 授权检查；未授权时自动从本轮候选工具集中移除 |
| `is_lightweight_proactive_safe` | `bool = False` | 声明该工具无主机、文件或外发副作用，允许在非 @/唤醒的轻量主动回复路径中保留（与配置项 `lightweight_proactive_tools` 白名单取并集） |

## 降级行为速查

| 函数 | 底层能力缺失时的行为 |
|---|---|
| `is_current` | 返回 `True`（放行） |
| `is_lightweight_proactive` | 返回 `False`（走常规路径） |
| `merged_text` / `merged_image_urls` | 返回 `""` / `[]` |
| `execution_denial` | 回退为管理员身份检查（非管理员返回拒绝原因，不降级为无条件放行） |
| `extract_quoted_message_images` | 返回 `[]` |
| `download_image_by_url` | **抛出 `RuntimeError`** |
| `is_text_part` / `is_image_part` / `is_embedding_provider` | 返回 `False` |
| `generate_with_persona` | 返回 `None` |
| `event.extras` 各读取器 | 返回对应类型的空默认值（`""` / `False` / `[]` / `{}`） |

## 相关文档

- [`api-contract.md`](./api-contract.md)：接口契约与降级规格
- [`plugin-quickstart.md`](./plugin-quickstart.md)：5 分钟入门
- [`design.md`](./design.md)：架构分层与兼容边界
