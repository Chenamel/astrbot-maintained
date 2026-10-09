# API 契约 · `astrbot/api/**` 新增模块（阶段 3）

> 本文件是阶段 3 的**唯一规格来源**。代码必须与本文件一致；不一致时先改本文件。
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

## 3. 模块清单

### 3.1 `astrbot/api/media/` — 媒体与图片输入契约

**解决的共性问题**：P1（插件顶层 import core 私有常量 → core 漂移即插件整体下线）、P4（`"<image_caption>"` 5 处硬编码）。

| 符号 | 类型 | 语义 |
|---|---|---|
| `IMAGE_CAPTION_MARKER` | `str` | 图片描述标记，固定 `"<image_caption>"` |
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

> **安全语义**：`execution_denial` 在补丁缺席时**不降级为放行**，而是回退到"仅管理员"这一上游既有强度。
> 本函数返回 `None` **不构成授权**——调用方（工具）仍须执行自身的权限闸门。

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
- **不复制** core 的实现逻辑（除两个常量镜像外，一律转发）。
- **不新增**依赖、不动配置 schema、不改任何既有符号签名。

## 5. 测试要求（`tests/maintained/`）

| 测试文件 | 覆盖 |
|---|---|
| `test_api_surface.py` | 五个模块可导入；`__all__` 与本文档一致；`_bridge` 不出现在 `__all__` |
| `test_api_media.py` | 常量非空且 `NOTICE` 含 `MESSAGE`；`IMAGE_CAPTION_MARKER` 正确；`has_visual_input` / `has_image_caption` 对伪造对象判定正确 |
| `test_api_turns.py` | 补丁缺席时 `is_current → True`、`mark_sent` no-op、`merged_*` 返回空、`reset* → False`、`available → False` |
| `test_api_delivery.py` | 缺席时 `code_task_spec → None`、`has_code_delivery → False`、`CODE_DELIVERY_FAILURE` 非空 |
| `test_api_permissions.py` | `is_admin` 判定正确；缺席时非管理员被拒、管理员放行（**不得**降级为无条件放行） |
| `test_api_proactive.py` | `proactive_switch_is_disabled → True`；缺席时 `is_lightweight_proactive → False` |

**测试不依赖运行中的 AstrBot**：用 `SimpleNamespace` 伪造 event / request / part。
**基线预期**：全部通过（因为断言的是"降级行为"）；阶段 4 恢复补丁后，`available()` 类断言会自动翻转，故此类断言写成"与 `available()` 一致"而非硬编码 `False`。

## 6. 台账要求

新增文件全部位于 `astrbot/**`，属受保护 core 文件 → **必须登记进 `maintained/installed_manifest.json`**（六铁律第 5 条）。
