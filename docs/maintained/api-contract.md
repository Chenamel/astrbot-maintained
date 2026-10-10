# API 契约 · `astrbot/api/**` 新增模块（阶段 3 + 阶段 5 追加）

> 本文件是新增 api 面的**唯一规格来源**。代码必须与本文件一致；不一致时先改本文件。
> 设计约束：对外冻结 + 只做加法；新模块一律落在 `astrbot/api/**`，**不修改任何既有 api 文件**。

## 1. 设计原则

1. **薄再导出 + 显式 `__all__`**：与官方 `astrbot/api/{event,star,provider,util}` 风格一致。
2. **优雅降级**：core 侧补丁模块在基线 4.28.2 上**不存在**（阶段 4 才恢复）。
   api 层必须在"补丁缺席"时**可导入、可调用、返回安全默认值**，补丁就位后**自动生效**，无需改 api 代码。
3. **零新增依赖**：只用标准库 + 既有 core。
4. **不改变既有行为**：api 层只读/转发，**不注册钩子、不改全局状态**（`reset*` 除外，见 §3.2）。

## 2. 降级契约（核心机制）

统一走内部桥 `astrbot/api/_bridge.py`（非公开面，外部禁止 import）：

```python
def resolve(module: str, name: str, default: Any = None) -> Any: ...
def capabilities() -> dict[str, bool]: ...
```

- `resolve` 惰性导入 core 侧符号；模块或属性缺失 → 返回 `default`，并**一次性** `logger.info` 记录能力缺失（不刷屏）。
- `capabilities()` 返回能力清单，供诊断与阶段 5 插件自检使用。

| 能力键 | 依赖的 core 符号 | 基线 4.28.2 上 | 阶段 4 后 |
|---|---|---|---|
| `turns.direct_turn` | `astrbot.core.utils.direct_turns.coordinator` | ❌ False | ✅ True |
| `delivery.code_policy` | `astrbot.core.code_delivery_policy` | ❌ False | ✅ True |
| `permissions.execution_policy` | `astrbot.core.code_delivery_policy.execution_denial` | ❌ False | ✅ True |
| `proactive.lightweight` | `astrbot.core.astr_main_agent._is_lightweight_proactive_request` | ❌ False | ✅ True |
| `media.unavailable_contract` | `astrbot.core.provider.entities.IMAGE_INPUT_UNAVAILABLE_NOTICE` | ❌ False | ✅ True |
| `content.parts` | `astrbot.core.agent.message.TextPart` | ❌ False | ✅ True |
| `runtime.helpers` | `astrbot.core.utils.io.download_image_by_url` | ❌ False | ✅ True |
| `embedding.provider` | `astrbot.core.provider.provider.EmbeddingProvider` | ❌ False | ✅ True |

## 3. 模块清单

### 3.0 阶段 5 追加：把插件剩余的 core 依赖也收敛到公开面

**背景**：参考插件当前有 **8 处** `from astrbot.core...`（6 处顶层 + 2 处函数内）。
经核实，这 8 个符号**官方公开面一个都没有**，而铁律 1 要求外部只允许 `import astrbot.api.*`。
故本层再追加 3 个模块（**仍为新增目录，不改既有 api 文件**）：

| core 符号 | 新落点 | 说明 |
|---|---|---|
| `astrbot.core.agent.message.TextPart` | `astrbot.api.content` | 内容部件类型；插件用它做 isinstance 判断与构造 |
| `astrbot.core.agent.message.ImageURLPart` | `astrbot.api.content` | 同上，成对提供 |
| `astrbot.core.utils.astrbot_path.get_astrbot_data_path` | `astrbot.api.runtime` | 运行时路径工具 |
| `astrbot.core.utils.io.download_image_by_url` | `astrbot.api.runtime` | 图片下载 |
| `astrbot.core.utils.quoted_message_parser.extract_quoted_message_images` | `astrbot.api.runtime` | 引用消息图片提取 |
| `astrbot.core.provider.provider.EmbeddingProvider` | `astrbot.api.embedding` | 嵌入提供者类型 |

**取舍说明**：这 5 个 core 路径在干净的 4.28.2 上**都存在**（不属"必须修"），
本阶段把它们也纳入公开面，是为了满足铁律 1 并给插件一个**统一且可降级**的依赖面。
本层对它们**只做转发**（经 `_bridge.resolve`），暂不提供替代实现；
若将来上游改名，再由本层补 fallback（届时属加法，不破坏契约）。

### 3.0.1 `astrbot/api/content/` — 内容部件

| 符号 | 类型 | 补丁/上游缺席时 |
|---|---|---|
| `available() -> bool` | 函数 | `False` |
| `TextPart` | 类（转发） | `None`（导入不报错） |
| `ImageURLPart` | 类（转发） | `None` |
| `is_text_part(part) -> bool` | 函数 | `False` |
| `is_image_part(part) -> bool` | 函数 | 仅识别 OpenAI 风格 `{"type": "image_url"}` |

> 注意：`TextPart`/`ImageURLPart` 在缺席时为 `None`，`isinstance(x, None)` 会抛 `TypeError`。
> 插件侧须用本模块提供的 `is_text_part(x)` / `is_image_part(x)` 做判定（缺席时返回 `False`），
> 而不是直接 `isinstance(x, TextPart)`。

### 3.0.2 `astrbot/api/runtime/` — 运行时工具

| 符号 | 类型 | 补丁/上游缺席时 |
|---|---|---|
| `available() -> bool` | 函数 | `False` |
| `get_astrbot_data_path() -> str` | 函数 | 回退到 `Path.cwd()/data` 的字面量路径 |
| `download_image_by_url(url, ...) -> Any` | 协程 | `raise RuntimeError`（明确失败，不静默） |
| `extract_quoted_message_images(event, comp) -> Any` | 协程 | 返回空列表（降级为"没有引用图"） |
| `HOOK_TIMING_ENHANCED` | `str` 常量 | 字面量 `"enhanced"`（与 core 同值） |
| `HOOK_TIMING_LEGACY` | `str` 常量 | 字面量 `"legacy"`（与 core 同值） |
| `hook_timing_mode() -> str` | 函数 | 返回 `"enhanced"`（＝本 fork 默认；非法值同样回落） |

**`hook_timing_mode()` 语义**：返回当前生效的「agent 完成钩子时序模式」。

- `enhanced`（默认）：完成钩子在**回复发出之前**触发，让审计/改写类插件先拿到控制权
  —— 这是本 fork 的架构优化（见 `hook-timing-impact.md`）。
- `legacy`：在**上游有对照的路径**上把钩子恢复到「回复先出、钩子后到」，
  行为与官方原版逐点一致；fork 独有的路径（图片降级兜底、末轮补生成）保留优化。

插件用法：自检当前模式，遇 `legacy` 时自行走保守路径或提示用户，避免静默故障。
该函数**不依赖 `_bridge` 能力键**，core 缺席/抛异常/返回非法值一律回落 `"enhanced"`。

### 3.0.3 `astrbot/api/embedding/` — 嵌入提供者

| 符号 | 类型 | 补丁/上游缺席时 |
|---|---|---|
| `available() -> bool` | 函数 | `False` |
| `EmbeddingProvider` | 类（转发） | `None` |
| `is_embedding_provider(obj) -> bool` | 函数 | 缺席时 `False` |

### 3.0.4 插件侧改造规则（阶段 5）

1. 插件中**所有** `from astrbot.core...` 改为 `from astrbot.api...`；
2. 顶层 import 一律包在 `try/except ImportError` 中并设降级默认值，
   使"被换回官方 core"时插件**仍能加载**（功能降级）而非整体下线；
3. 类型判定改用本层提供的 `is_*` 辅助函数，禁止直接 `isinstance(x, 可能为 None 的类)`。

### 3.1 `astrbot/api/media/` — 媒体与图片输入契约

**解决的共性问题**：P1（插件顶层 import core 私有常量 → core 漂移即插件整体下线）、P4（`"<image_caption>"` 5 处硬编码）。

| 符号 | 类型 | 语义 |
|---|---|---|
| `IMAGE_CAPTION_MARKER` | `str` | 图片描述标记，固定 `"<image_caption>"`。**权威定义在 core**（`astrbot.core.provider.entities`），本层经 `resolve` 转发、缺失时用同值字面量兜底 |
| `IMAGE_INPUT_UNAVAILABLE_MESSAGE` | `str` | 给**用户**看的文案 |
| `IMAGE_INPUT_UNAVAILABLE_NOTICE` | `str` | 给**模型**看的防幻觉指令 |
| `has_visual_input(request) -> bool` | 函数 | `request` 是否携带真实视觉证据（`image_urls` 或 `ImageURLPart` / `image_url` dict） |
| `has_image_caption(parts) -> bool` | 函数 | `parts` 中是否存在图片描述部件 |
| `image_input_available(request) -> bool` | 函数 | 视觉证据是否可用（等价 `not request.image_input_unavailable`，缺失时按有无视觉输入判断） |
| `available() -> bool` | 函数 | core 契约是否就位 |

**常量一致性要求（P1 修复的关键）**：
- core 侧存在时**必须原样转发** core 的值（插件有 `part.text != NOTICE` 的**字符串比较**，值不一致会失效）。
- core 侧缺失时使用**本地镜像常量**，文本与 core 完全一致：

  ```
  MESSAGE = "当前看不到图片，请重新发送。"
  NOTICE  = "[Image unavailable: no visual evidence was received. "
            "Do not infer or describe the image from history, filenames or surrounding text. "
            f"Reply only: {MESSAGE}]"
  ```
- 常量解析在**模块导入时**完成（插件顶层 import 场景，必须导入即得值）。

### 3.2 `astrbot/api/turns/` — 直报回合

**解决的共性问题**：P2 的一半（插件需重置回合状态但不能 import 私有模块）。

| 符号 | 类型 | 语义 | 补丁缺席时 |
|---|---|---|---|
| `available() -> bool` | 函数 | 能力是否就位 | `False` |
| `is_current(event) -> bool` | 函数 | 事件是否代表当前回合 | **`True`**（无回合概念 = 永远当前，保持旧行为） |
| `mark_sent(event) -> None` | 函数 | 标记回合已发出回复 | no-op |
| `turn_version(event) -> int \| None` | 函数 | 回合版本号 | `None` |
| `merged_text(event) -> str` | 函数 | 合并后的同账号消息文本 | `""` |
| `merged_image_urls(event) -> list[str]` | 函数 | 合并后的图片 URL（去重） | `[]` |
| `reset(unified_msg_origin) -> bool` | 函数 | 清空指定会话的回合状态 | `False` |
| `reset_all() -> bool` | 函数 | 清空全部回合状态 | `False` |

> `reset*` 是本层唯一有副作用的函数，语义等价于 core `coordinator.reset/reset_all`。

### 3.3 `astrbot/api/delivery/` — 交付策略

**解决的共性问题**：P3 的一部分（策略纯函数对外可用）。

| 符号 | 类型 | 语义 | 补丁缺席时 |
|---|---|---|---|
| `available() -> bool` | 函数 | 能力是否就位 | `False` |
| `CODE_DELIVERY_FAILURE` | `str` | 空交付修复失败时的兜底文案 | 本地镜像 `"这次没生成完整代码，可以再试一次"` |
| `code_task_spec(event) -> tuple[str, str] \| None` | 函数 | 代码任务规格 `(文本, 语言)` | `None` |
| `has_code_delivery(text, language="") -> bool` | 函数 | 文本是否构成了真实源码交付 | `False` |

### 3.4 `astrbot/api/permissions/` — 权限与执行授权

**解决的共性问题**：P6（权限双模型）。

| 符号 | 类型 | 语义 | 补丁缺席时 |
|---|---|---|---|
| `available() -> bool` | 函数 | 执行策略引擎是否就位 | `False` |
| `is_admin(event, config) -> bool` | 函数 | 纯判定：发送者是否在 `config["admins_id"]` | 本函数**不依赖补丁**，始终可用 |
| `execution_denial(event, config) -> str \| None` | 函数 | `None`=放行；否则为拒绝原因文本 | **回退为纯管理员判定**：非管理员返回拒绝文本，管理员放行 |
| `EXECUTION_NOT_AUTHORIZED` | `str` | 无法授权时的固定拒绝原因（可读、可断言） | 本地常量，始终可用 |

> **安全语义**：`execution_denial` 在补丁缺席时**不降级为放行**，而是回退到"仅管理员"这一上游既有强度。
> 本函数返回 `None` **不构成授权**——调用方（工具）仍须执行自身的权限闸门。

> **拒绝原因的两种口径**：`execution_denial` 的返回值**只是文本**，不构成符号级契约。
> - `EXECUTION_NOT_AUTHORIZED`：确定的"未授权"（**公开常量**，可读、可断言）；
> - 策略引擎在场但抛异常时，返回 **fail-closed 的内部兜底文本**
>   （模块私有 `_EXECUTION_POLICY_UNAVAILABLE`；**故意不导出、不进 `__all__`** ——
>   它是内部错误兜底文案，不应对调用方形成版本承诺）。
>
> ⇒ 调用方只需判断「返回值是否为 `None`」，**不要**对具体文本做等值断言（除非用上面的公开常量）。
> 该安排遵循 `project_rules.md` §9：不允许"公开名字却不在 `__all__`/契约/测试里"的定义存在。

### 3.5 `astrbot/api/proactive/` — 主动场景

**约束**：六铁律第 6 条 —— 主动回复开关恒为关闭，本层**不得**提供任何开启途径。

| 符号 | 类型 | 语义 | 补丁缺席时 |
|---|---|---|---|
| `available() -> bool` | 函数 | 轻量主动判定是否就位 | `False` |
| `proactive_switch_is_disabled() -> bool` | 函数 | **恒返回 `True`**，声明铁律 6 不变量 | 恒 `True` |
| `is_lightweight_proactive(event) -> bool` | 函数 | 该请求是否被判定为轻量主动场景 | **`False`**（fail-closed：宁可走完整路径，也不误入轻量路径） |

## 4. 明确不做

- **不修改** `astrbot/api/__init__.py`、`all.py`、`message_components.py`、`web.py` 及 `{event,star,provider,util,platform}/`。
- **不提供**主动回复的开启/注册入口。
- **不复制** core 的实现逻辑（除常量镜像外，一律转发；**镜像的权威定义在 core**，本层只做转发 + 同值兜底）。
- **不新增**依赖、不动配置 schema、不改任何既有符号签名。

## 5. 测试要求（`tests/maintained/`）

| 测试文件 | 覆盖 |
|---|---|
| `test_api_surface.py` | 八个模块可导入；`__all__` 与本文档一致；`_bridge` 不出现在 `__all__`；能力清单键齐全 |
| `test_api_media.py` | 常量非空且 `NOTICE` 含 `MESSAGE`；`IMAGE_CAPTION_MARKER` 正确；`has_visual_input` / `has_image_caption` 对伪造对象判定正确 |
| `test_api_turns.py` | 补丁缺席时 `is_current → True`、`mark_sent` no-op、`merged_*` 返回空、`reset* → False`、`available → False` |
| `test_api_delivery.py` | 缺席时 `code_task_spec → None`、`has_code_delivery → False`、`CODE_DELIVERY_FAILURE` 非空 |
| `test_api_permissions.py` | `is_admin` 判定正确；缺席时非管理员被拒、管理员放行（**不得**降级为无条件放行） |
| `test_api_proactive.py` | `proactive_switch_is_disabled → True`；缺席时 `is_lightweight_proactive → False` |
| `test_api_content.py` | 缺席时 `is_text_part` / `is_image_part` 判定与容错；OpenAI 风格 dict |
| `test_api_runtime.py` | 数据目录为绝对路径；缺席时下载**响亮失败**、引用图返回空表 |
| `test_api_embedding.py` | 缺席时 `is_embedding_provider → False`；容错 |
| `test_manifest_guard.py` | 仓工作树↔台账自洽；台账只含 core、`proactive_must_remain_disabled` 为 `True`、条数钉 |
| `test_api_frozen.py` | 上游 api 文件相对 `baseline/v4.28.2` 零改动（白名单=9 个新增文件） |
| `test_tools_check_drift.py` / `test_tools_apply_patches.py` | 工具链：漂移检测、预演不写、写前备份、源损坏中止、退出码 |

**测试不依赖运行中的 AstrBot**：用 `SimpleNamespace` 伪造 event / request / part。
**基线预期**：全部通过（因为断言的是"降级行为"）；阶段 4 恢复补丁后，`available()` 类断言会自动翻转，故此类断言写成"与 `available()` 一致"而非硬编码 `False`。

## 6. 台账要求

新增文件全部位于 `astrbot/**`，属受保护 core 文件 → **必须登记进 `maintained/installed_manifest.json`**（六铁律第 5 条）。

## 7. 消费方自检（只读）

维护版插件（私有仓 `astrbot-extras`）提供一条**只读**自检命令，用于运行时确认公开面是否就位：

```
enhance api-status        # 仅管理员
```

**实现约束**（发布前请对齐）：

1. **只读**：仅调用各模块公开的 `available()`，不写任何状态；
2. **只走公开面**：遍历 `astrbot.api.{content,delivery,embedding,media,permissions,proactive,runtime,turns}`，
   **禁止 import `astrbot.api._bridge`**（非公开面）；
3. **不碰开关**：尤其不得读写 `active_reply` 相关配置（六铁律第 6 条）；
4. **可降级**：任一模块缺失时只报告 `unavailable`，不抛异常、不影响插件加载。

**输出语义**：`installed` = 维护版 core 提供了该能力；`degraded` = core 侧支持缺失（对应功能自动降级）。

**实测样例**（维护版实例，8 个模块全部就位）：

```
Maintained AstrBot API surface (read-only)

  astrbot.api.content: installed
  astrbot.api.delivery: installed
  astrbot.api.embedding: installed
  astrbot.api.media: installed
  astrbot.api.permissions: installed
  astrbot.api.proactive: installed
  astrbot.api.runtime: installed
  astrbot.api.turns: installed
```
