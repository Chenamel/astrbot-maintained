# API 契约 · `astrbot/api/**` 扩展模块

> 本文件定义 `astrbot/api/**` 下扩展模块的接口规格、事件附加字段契约与降级行为。
> 扩展模块均以独立子模块形式提供，不修改上游既有 `astrbot/api` 文件。

## 1. 设计原则

1. 薄转发与显式导出：每个扩展子模块均声明显式 `__all__`，与上游 `astrbot/api/{event,star,provider,util}` 风格保持一致。
2. 安全降级：当底层 core 未安装对应扩展实现时，api 层仍可正常导入和调用，并返回安全默认值；底层实现就位后自动生效，无需修改调用方代码。
3. 零新增外部依赖：仅使用 Python 标准库与既有 core 模块。
4. 无副作用转发：除 `turns.reset` 与 `turns.reset_all` 及 `event.extras.set_visual_unavailable` 外，api 层函数均为只读查询或无状态转发，不在导入时注册全局钩子或改写全局状态。

## 2. 降级契约与桥接机制

所有扩展模块统一通过内部桥接模块 `astrbot/api/_bridge.py`（内部实现，外部插件禁止导入）解析底层实现：

```python
def resolve(module: str, name: str, default: Any = None) -> Any: ...
def capabilities() -> dict[str, bool]: ...
```

- `resolve` 惰性导入 core 侧符号；当目标模块或属性缺失时返回 `default`，并在首次缺失时记录一条 `logger.info` 日志。
- `capabilities()` 返回各扩展能力的就位状态字典，供运行时诊断与插件自检使用。

| 能力键 | 依赖的 core 符号 | 原版 core | 维护版 core |
|---|---|---|---|
| `turns.direct_turn` | `astrbot.core.utils.direct_turns.coordinator` | ❌ False | ✅ True |
| `delivery.code_policy` | `astrbot.core.code_delivery_policy` | ❌ False | ✅ True |
| `permissions.execution_policy` | `astrbot.core.code_delivery_policy.execution_denial` | ❌ False | ✅ True |
| `proactive.lightweight` | `astrbot.core.astr_main_agent._is_lightweight_proactive_request` | ❌ False | ✅ True |
| `proactive.persona` | `astrbot.core.proactive_persona.generate_with_persona` | ❌ False | ✅ True |
| `media.unavailable_contract` | `astrbot.core.provider.entities.IMAGE_INPUT_UNAVAILABLE_NOTICE` | ❌ False | ✅ True |
| `content.parts` | `astrbot.core.agent.message.TextPart` | ❌ False | ✅ True |
| `runtime.helpers` | `astrbot.core.utils.io.download_image_by_url` | ❌ False | ✅ True |
| `embedding.provider` | `astrbot.core.provider.provider.EmbeddingProvider` | ❌ False | ✅ True |

## 3. 模块与符号规格

### 3.0 常用 core 符号的公开转发

原版 `astrbot.api` 未导出消息段类型、数据目录路径、图片下载与 Embedding 类型。以下三个模块将这些常用符号纳入 `astrbot/api/` 统一转发，并提供缺失时的安全降级：

| core 符号 | 公开模块落点 | 说明 |
|---|---|---|
| `astrbot.core.agent.message.TextPart` | `astrbot.api.content` | 文本内容部件类型 |
| `astrbot.core.agent.message.ImageURLPart` | `astrbot.api.content` | 图片内容部件类型 |
| `astrbot.core.utils.astrbot_path.get_astrbot_data_path` | `astrbot.api.runtime` | 运行时数据目录路径获取 |
| `astrbot.core.utils.io.download_image_by_url` | `astrbot.api.runtime` | 远程图片下载 |
| `astrbot.core.utils.quoted_message_parser.extract_quoted_message_images` | `astrbot.api.runtime` | 引用消息中的图片提取 |
| `astrbot.core.provider.provider.EmbeddingProvider` | `astrbot.api.embedding` | 向量化 provider 基类 |

上述 core 符号在当前上游基线（`baseline/*`）中均已存在，本层通过 `_bridge.resolve` 原样转发；若未来上游移动或重命名内部路径，可在本层透明补齐兼容转发，插件无需改动导入语句。

### 3.0.1 `astrbot/api/content/` — 内容部件

| 符号 | 类型 | 底层符号缺失时的返回值 |
|---|---|---|
| `available() -> bool` | 函数 | `False` |
| `TextPart` | 类转发 | `None`（导入不报错） |
| `ImageURLPart` | 类转发 | `None` |
| `is_text_part(part) -> bool` | 函数 | `False` |
| `is_image_part(part) -> bool` | 函数 | 仅识别 OpenAI 风格 `{"type": "image_url"}` 字典 |

> 注意：当 `TextPart` 或 `ImageURLPart` 为 `None` 时，直接调用 `isinstance(x, TextPart)` 会抛出 `TypeError`。插件必须使用 `is_text_part(x)` 与 `is_image_part(x)` 进行类型判定。

### 3.0.2 `astrbot/api/runtime/` — 运行时工具

| 符号 | 类型 | 底层符号缺失时的返回值 |
|---|---|---|
| `available() -> bool` | 函数 | `False` |
| `get_astrbot_data_path() -> str` | 函数 | 回退为 `str(Path.cwd() / "data")` |
| `download_image_by_url(url, ...) -> Any` | 协程 | 抛出 `RuntimeError`（显式报错，不静默返回空值） |
| `extract_quoted_message_images(event, comp) -> Any` | 协程 | 返回空列表 `[]` |
| `HOOK_TIMING_ENHANCED` | `str` 常量 | `"enhanced"` |
| `HOOK_TIMING_LEGACY` | `str` 常量 | `"legacy"` |
| `hook_timing_mode(event=None) -> str` | 函数 | 返回当前生效模式；未配置、非法值或底层缺失时回落 `"legacy"` |
| `format_local_time(value, with_seconds=True, with_date=True) -> str` | 函数 | 底层缺失或无法解析时原样返回 `str(value)` |

`format_local_time()` 时钟规则：
- 数据库 `TimestampMixin` 存储的时间戳均为 naive UTC（`datetime.now(timezone.utc)` 且 `timezone=False`），而日志、用户界面与系统提示词均使用本地时间。
- 凡是将存储时间戳拼入展示文本或模型提示词的场景，均须调用本函数转换为本地时间，避免同一段上下文混用两套相差 8 小时的时区。
- 支持输入 `datetime`（naive 视为 UTC）、ISO-8601 字符串与秒级时间戳；解析失败时原样返回字符串，不抛异常。

`hook_timing_mode()` 时序规则：
- `"legacy"`：在有上游对照的路径上保持「先发送回复、后触发完成钩子」的上游默认时序。
- `"enhanced"`：在发送回复前先触发完成钩子，供审计或改写类插件介入（通过 `agent_runner.config.misc.hook_timing_mode` 配置）。

### 3.0.3 `astrbot/api/embedding/` — 嵌入提供者

| 符号 | 类型 | 底层符号缺失时的返回值 |
|---|---|---|
| `available() -> bool` | 函数 | `False` |
| `EmbeddingProvider` | 类转发 | `None` |
| `is_embedding_provider(obj) -> bool` | 函数 | `False` |

### 3.0.4 插件侧调用约定

1. 外部插件统一从 `astrbot.api.*` 导入符号，不直接导入 `astrbot.core.*`。
2. 顶层导入建议配合 `available()` 检查或 `try/except ImportError` 兜底，确保切换到官方原版 core 时插件仍能加载。
3. 类型判定统一调用 `is_*` 辅助函数，不直接对可能为 `None` 的转发类调用 `isinstance`。

### 3.1 `astrbot/api/media/` — 媒体与图片输入契约

提供图片输入可用性判定与防幻觉提示常量。

| 符号 | 类型 | 语义 |
|---|---|---|
| `IMAGE_CAPTION_MARKER` | `str` | 图片描述标记常量，固定为 `"<image_caption>"` |
| `IMAGE_INPUT_UNAVAILABLE_MESSAGE` | `str` | 图片不可用时展示给用户的提示文案 |
| `IMAGE_INPUT_UNAVAILABLE_NOTICE` | `str` | 图片不可用时注入给模型的防幻觉系统指令 |
| `has_visual_input(request) -> bool` | 函数 | 判断 `request` 是否携带真实视觉输入（`image_urls` 或 `ImageURLPart` / `image_url` dict） |
| `has_image_caption(parts) -> bool` | 函数 | 判断 `parts` 中是否包含带 `IMAGE_CAPTION_MARKER` 的图片转述段落 |
| `image_input_available(request) -> bool` | 函数 | 判断视觉输入是否可用（等价于 `not request.image_input_unavailable`，缺失时按是否有视觉输入判定） |
| `available() -> bool` | 函数 | 底层媒体契约是否就位 |

常量镜像一致性要求：
- 当底层 `astrbot.core.provider.entities` 存在对应常量时原样转发；缺失时回退为与 core 完全一致的本地字面量：

```python
MESSAGE = "当前看不到图片，请重新发送。"
NOTICE  = (
    "[Image unavailable: no visual evidence was received. "
    "Do not infer or describe the image from history, filenames or surrounding text. "
    f"Reply only: {MESSAGE}]"
)
```

### 3.2 `astrbot/api/turns/` — 直发回合

提供直发回合合并文本、图片与回合状态访问接口。

| 符号 | 类型 | 语义 | 底层缺失时的返回值 |
|---|---|---|---|
| `available() -> bool` | 函数 | 回合协调器是否就位 | `False` |
| `is_current(event) -> bool` | 函数 | 事件是否处于当前最新回合 | `True`（fail-open） |
| `mark_sent(event) -> None` | 函数 | 标记本回合已发送回复 | no-op |
| `turn_version(event) -> int \| None` | 函数 | 获取回合版本号 | `None` |
| `merged_text(event) -> str` | 函数 | 获取合并后的同发送者消息文本 | `""` |
| `merged_image_urls(event) -> list[str]` | 函数 | 获取合并并去重后的图片 URL 列表 | `[]` |
| `reset(unified_msg_origin) -> bool` | 函数 | 清空指定会话的回合状态 | `False` |
| `reset_all() -> bool` | 函数 | 清空全部会话的回合状态 | `False` |

### 3.3 `astrbot/api/delivery/` — 交付策略

提供代码交付完整性与代码任务识别接口。

| 符号 | 类型 | 语义 | 底层缺失时的返回值 |
|---|---|---|---|
| `available() -> bool` | 函数 | 交付策略模块是否就位 | `False` |
| `CODE_DELIVERY_FAILURE` | `str` | 代码未完整交付时的兜底提示文案 | `"这次没生成完整代码，可以再试一次"` |
| `code_task_spec(event) -> tuple[str, str] \| None` | 函数 | 提取代码任务规格 `(任务文本, 目标语言)` | `None` |
| `has_code_delivery(text, language="") -> bool` | 函数 | 判断文本是否包含非省略的真实代码块 | `False` |

### 3.4 `astrbot/api/permissions/` — 权限与执行授权

提供管理员身份判定与单次执行意图授权判定接口。

| 符号 | 类型 | 语义 | 底层缺失时的返回值 |
|---|---|---|---|
| `available() -> bool` | 函数 | 执行授权策略引擎是否就位 | `False` |
| `is_admin(event, config) -> bool` | 函数 | 判断发送者是否在 `config["admins_id"]` 中 | 始终可用 |
| `execution_denial(event, config) -> str \| None` | 函数 | 返回 `None` 表示放行；非 `None` 为拒绝原因文本 | 回退为纯管理员校验（非管理员返回拒绝文本） |
| `EXECUTION_NOT_AUTHORIZED` | `str` | 未获授权时的公开拒绝原因常量 | 本地常量，始终可用 |

> 安全约束：`execution_denial` 在底层策略缺失时回退为管理员校验，绝不降级为无条件放行。调用方仅需判断返回值是否为 `None`，不要对内部异常兜底文本做等值断言。

### 3.5 `astrbot/api/proactive/` — 主动场景与插件能力发现约定

本模块提供主动场景判定标记、经过 `on_llm_request` 钩子链的人格感知生成与群聊历史写回接口，不内置主动触发调度器。

| 符号 | 类型 | 语义 | 底层缺失时的返回值 |
|---|---|---|---|
| `available() -> bool` | 函数 | 轻量主动判定是否就位 | `False` |
| `proactive_switch_is_disabled() -> bool` | 函数 | 恒返回 `True`，表示本 API 层不内置主动触发入口 | `True` |
| `is_lightweight_proactive(event) -> bool` | 函数 | 判断请求是否属于轻量主动场景 | `False`（fail-closed） |
| `persona_available() -> bool` | 函数 | 人格感知生成是否就位 | `False` |
| `generate_with_persona(context, event, prompt, ...) -> LLMResponse \| None` | 协程 | 先执行 `on_llm_request` 钩子链（并注入 `self_identity_note`）再调用模型生成文本 | `None`（fail-closed） |
| `record_bot_message(context, event, text) -> bool` | 协程 | 将机器人主动回复写回历史库（`sender_id="bot"`） | `False` |
| `record_user_message(context, event, text, max_messages=700) -> bool` | 协程 | 将群消息写回历史库；只要记录已在库中即返回 `True` | `False` |

#### `record_*` 的幂等返回值定义

若把「记录已存在」当作失敗返回 `False`，调用方会在正常幂等跳过时打出大量误报警告，淹没真实的数据库写入错误。因此返回值按最终状态定义：只要调用结束时该条消息已存在于历史库中即返回 `True`，仅在跳过或写入失败时返回 `False`。

#### `generate_with_persona` 的执行链

`Context.llm_generate()` 与 `Context.tool_loop_agent()` 直接调用底层 provider，不触发 `on_llm_request` 钩子，导致挂载在该钩子上的人格（`PERSONA_PLUGIN`）、长期记忆（`MEMORY_PLUGIN`）与群上下文（`CONTEXT_PLUGIN`）插件无法注入上下文。`generate_with_persona` 先构造 `ProviderRequest`、注入机器人自身账号归属说明（`self_identity_note`），再调用 `call_event_hook(event, EventType.OnLLMRequestEvent, req)`，最后将修改后的请求交由 provider 生成。该函数只负责生成文本，不执行消息发送。

#### 插件能力发现契约（鸭子类型方法约定）

core 内部不硬编码任何插件目录名，而是通过遍历已激活插件类（`star_registry`）按方法名发现主动回复协同能力（调用抛异常时记录警告并 fail-closed）：

| 约定方法签名 | 调用时机 | 未实现或异常时的回退行为 |
|---|---|---|
| `is_trusted_lightweight_proactive(event) -> bool` | `astr_main_agent._is_lightweight_proactive_request` 校验轻量主动标记是否可信 | 返回 `False`，按常规消息路径处理 |
| `finish_proactive_request(event) -> Any` | `tool_loop_agent_runner._finish_proactive_request` 在主动请求完成时执行收尾 | 跳过收尾（幂等标记照常置位） |

### 3.6 `astrbot/api/event/extras.py` — 事件附加字段契约

集中定义跨插件与 core 共享的 9 个事件附加字段键名常量、10 个带类型校验的读取函数与 1 个写入函数，消除对 `event.get_extra("_enhance_*")` 的裸读与类型异常：

#### 键名常量

```python
ACTIVE_REPLY_TOKEN = "_enhance_active_reply_token"
VISUAL_REQUESTED = "_enhance_visual_requested"
VISUAL_UNAVAILABLE = "_enhance_visual_unavailable"
OWNED_IMAGE_URLS = "_enhance_owned_image_urls"
OWNED_QUOTE_IMAGE_URLS = "_enhance_owned_quote_image_urls"
FOLLOWUP_DIRECT = "_enhance_followup_direct"
FOLLOWUP_TASK = "_enhance_followup_task"
PROACTIVE_LIGHTWEIGHT = "_enhance_proactive_lightweight"
ACTIVE_REPLY_TRIGGERED = "_enhance_active_reply_triggered"
```

#### 读写器签名与降级默认值

| 函数 | 返回类型 | 缺失或类型不符时的默认值 |
|---|---|---|
| `active_reply_token(event)` | `str` | `""` |
| `is_active_reply(event)` | `bool` | `False` |
| `visual_requested(event)` | `bool` | `False` |
| `visual_unavailable(event)` | `bool` | `False` |
| `owned_image_urls(event)` | `list[str]` | `[]`（若传入单个非空字符串则自动包装为单元素列表） |
| `owned_quote_image_urls(event)` | `dict[str, list[str]]` | `{}` |
| `followup_direct(event)` | `bool` | `False` |
| `followup_task(event)` | `str` | `""` |
| `proactive_lightweight(event)` | `bool` | `False` |
| `active_reply_triggered(event)` | `bool` | `False` |
| `set_visual_unavailable(event, flag: bool)` | `None` | 事件不支持 `set_extra` 时安全忽略 |

## 4. 兼容边界

- 不修改上游既有的 `astrbot/api/__init__.py`、`all.py`、`message_components.py`、`web.py` 及 `{event,star,provider,util,platform}/__init__.py`。
- 不在 `astrbot/api/` 层内置主动回复触发器。
- 除防幻觉与错误兜底常量镜像外，不在 `astrbot/api/` 层复制 core 业务逻辑。

## 5. 契约测试矩阵（`tests/maintained/`）

| 测试文件 | 校验内容 |
|---|---|
| `test_api_surface.py` | 各扩展模块可导入、`__all__` 与本文档一致、`_bridge` 不出现在 `__all__`、能力键齐全 |
| `test_api_doc_gate.py` | 每个公开模块具备 docstring、显式 `__all__`、符号 docstring 与常量注释 |
| `test_api_media.py` | 媒体常量非空且一致，`has_visual_input` / `has_image_caption` / `image_input_available` 判定准确 |
| `test_api_turns.py` | 回合状态查询、合并文本/图片与重置接口在就位及降级态下的行为 |
| `test_api_delivery.py` | `code_task_spec`、`has_code_delivery` 与 `CODE_DELIVERY_FAILURE` 判定 |
| `test_api_permissions.py` | `is_admin` 与 `execution_denial` 权限判定，确保缺失时不降级为放行 |
| `test_api_proactive.py` | `proactive_switch_is_disabled`、`is_lightweight_proactive`、`generate_with_persona` 与 `record_*` |
| `test_api_content.py` | `is_text_part` / `is_image_part` 对内容段对象与 OpenAI 字典的容错判定 |
| `test_api_runtime.py` | 数据目录、本地时间换算、引用图提取及下载缺失时抛 `RuntimeError` |
| `test_api_embedding.py` | `is_embedding_provider` 类型判定与降级容错 |
| `test_event_extras.py` | `api.event.extras` 9 个常量与 11 个读写函数在正常值、异常类型与无 `extras` 替身下的表现 |
| `test_api_frozen.py` | 上游既有 `astrbot/api/**` 文件相对当前 `baseline/*` 锚点零改动 |
| `test_manifest_guard.py` | 仓库工作树与 `maintained/installed_manifest.json` 哈希一致 |

## 6. 台账登记要求

所有位于 `astrbot/**` 下的新增或修改文件均属于受保护 core 文件，必须同步更新 `maintained/installed_manifest.json` 中的 SHA-256 哈希。

## 7. 运行时只读自检代码

插件或运维脚本可通过以下只读代码检查当前环境中各扩展模块的就位状态：

```python
from astrbot.api import content, delivery, embedding, media, permissions, proactive, runtime, turns

MODULES = (content, delivery, embedding, media, permissions, proactive, runtime, turns)
for mod in MODULES:
    print(f"{mod.__name__}: {'installed' if mod.available() else 'degraded'}")
```

输出 `installed` 表示底层实现已就位；输出 `degraded` 表示当前运行在未打补丁的原版 core 上，对应接口自动按本契约返回安全默认值。
