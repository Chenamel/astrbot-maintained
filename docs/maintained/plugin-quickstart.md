# 插件作者 5 分钟入门

本页通过最小可运行示例演示如何在插件中调用维护分支的扩展 API，以及这些 API 在上游原版 AstrBot 环境下的降级行为。完整接口规格见 [`api-contract.md`](./api-contract.md)，调用细节见 [`api-reference.md`](./api-reference.md)，安装与启动见 [`install.md`](./install.md)。

## 1. 最小可运行插件

新建目录 `data/plugins/hello_fork/`，创建以下两个文件。

`metadata.yaml`：

```yaml
name: hello_fork
desc: 演示如何使用维护分支的公开 API
author: plugin-author
version: 0.1.0
```

`main.py`：

```python
from astrbot.api import turns
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class HelloFork(Star):
    """Smallest plugin that reads a maintained-fork API."""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

    @filter.command("forkhello")
    async def hello(self, event: AstrMessageEvent):
        # turns.is_current: 本回合是否仍未回复；底层能力未就位时 fail-open 返回 True
        already = not turns.is_current(event)
        yield event.plain_result(
            f"API 就位={turns.available()}，本回合已回复={already}"
        )
        turns.mark_sent(event)
```

重载插件后，在聊天中发送 `/forkhello` 即可收到回执。
每个扩展模块均提供 `available() -> bool`；返回 `False` 表示当前环境未安装对应底层实现，此时模块内的其余函数会按 [`api-contract.md`](./api-contract.md) 定义的默认值安全降级，不会抛出未捕获异常。

> 插件应仅从 `astrbot.api.*` 导入符号。直接导入 `astrbot.core.*` 内部路径会在核心版本变动或切换回官方原版时因顶层 `ImportError` 导致整个插件无法加载。

## 2. 人格感知生成

上游的 `Context.llm_generate()` 与 `Context.tool_loop_agent()` 直接调用底层 provider，跳过了 `on_llm_request` 钩子，导致挂载在该钩子上的人格、长期记忆和群上下文插件无法参与生成。
`generate_with_persona` 会先构造 `ProviderRequest` 并执行 `on_llm_request` 钩子，再调用底层 provider：

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.proactive import generate_with_persona, persona_available
from astrbot.api.star import Context, Star


class HelloFork(Star):
    """Generate one persona-aware line on demand."""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

    @filter.command("forksay")
    async def say(self, event: AstrMessageEvent):
        if not persona_available():
            yield event.plain_result("人格生成能力未就位，已跳过。")
            return
        resp = await generate_with_persona(
            self.context,
            event,
            "用一句话向群里问好",
            system_prompt="保持简洁、口语化",
        )
        if resp is not None:
            yield event.plain_result(resp.completion_text)
```

`generate_with_persona(context, event, prompt, system_prompt="", image_urls=None, chat_provider_id=None, timeout=None)` 为异步协程，返回 `LLMResponse | None`。该函数只负责生成文本，不执行发送；底层能力未就位或请求被钩子中止时返回 `None`（fail-closed）。

## 3. 模块速查

下表所列模块均位于 `astrbot/api/**`，统一通过 `from astrbot.api import <模块>` 导入。`astrbot.api.event`、`platform`、`provider`、`star` 等上游既有公开模块的用法保持不变。

| 模块 | 一句话用途 | 最小调用示例 | 底层能力未就位时的降级返回值 |
|---|---|---|---|
| `turns` | 合并同账号直发回合、标记本回合已回复 | `turns.is_current(event)`；`turns.mark_sent(event)` | `is_current` → `True`，`mark_sent` 为 no-op，合并值返回空 |
| `delivery` | 判定文本是否包含完整源码交付 | `delivery.has_code_delivery(text)` | `False`；`code_task_spec` → `None` |
| `permissions` | 管理员判定与单次执行授权判定 | `permissions.execution_denial(event, config)` | 回退为「仅管理员」判定，不放行非管理员；`is_admin` 始终可用 |
| `media` | 图片输入可用性判定与防幻觉常量 | `media.has_visual_input(request)` | 常量使用与 core 同值的本地镜像；判定函数按请求字段工作 |
| `content` | 文本与图片内容部件的类型判定 | `content.is_text_part(part)` | 部件类型解析为 `None`，判定返回 `False` |
| `runtime` | 数据目录、图片下载、本地时间、钩子时序模式 | `runtime.hook_timing_mode()` | 模式回落 `"legacy"`；`download_image_by_url` 抛出 `RuntimeError` |
| `embedding` | 嵌入 provider 的类型判定 | `embedding.is_embedding_provider(obj)` | `False` |
| `proactive` | 轻量主动标记、人格生成、历史写回 | `proactive.proactive_switch_is_disabled()` | 恒 `True`；轻量判定 `False`；生成 `None`；写回 `False` |
| `event.extras` | 事件附加字段常量与带类型兜底的读写器 | `extras.is_active_reply(event)` | 类型不符或字段缺失时返回安全默认值（`False` / `""` / `[]` / `{}`） |

`api.proactive` 不提供主动触发入口：官方内置的 `active_reply.enable` 与插件自带的主动开关各自独立，同一实例同一时间只应启用一套，避免单条群消息触发两次主动回复。

各模块的完整符号表、参数与返回值契约见 [`api-contract.md`](./api-contract.md) §3。

## 4. 降级机制

所有扩展模块均通过内部桥接层 `astrbot/api/_bridge.py`（内部实现，插件请勿直接导入）的 `resolve(module, name, default)` 惰性解析底层符号：当模块或属性不存在时返回预设的安全默认值，且仅在首次缺失时记录一条日志，不会抛出 `ImportError`。

- **安全与生成相关接口采用 fail-closed**：`execution_denial` 回退为「仅管理员」校验；`is_lightweight_proactive` 返回 `False`；`generate_with_persona` 返回 `None`。
- **状态查询接口保持旧行为（fail-open）**：`turns.is_current` 返回 `True`，`mark_sent` 为空操作，`reset*` 返回 `False`。
- `permissions.execution_denial` 返回 `None` 仅代表通过执行意图检查，调用方仍须执行自身的权限守卫；请仅判断返回值是否为 `None`，不要对拒绝原因字符串做精确等值断言。

## 5. 能力自检

在不确定底层扩展是否就位时，可先查询 `available()`：

```python
from astrbot.api import delivery, permissions, proactive, turns

print({
    "turns": turns.available(),
    "delivery": delivery.available(),
    "permissions": permissions.available(),
    "proactive": proactive.available(),
})
```

返回 `False` 表示当前环境未包含对应 core 扩展，按 §3 的降级返回值处理即可。

## 6. 延伸阅读

| 需求 | 对应文档 |
|---|---|
| 查阅每个函数的参数、返回值与调用示例 | [`api-reference.md`](./api-reference.md) |
| 查阅接口签名、事件附加字段契约与降级规格 | [`api-contract.md`](./api-contract.md) |
| 了解维护分支相对上游的差异与边界 | [`fork-advantages.md`](./fork-advantages.md) |
| 安装、启动与完整性校验 | [`install.md`](./install.md) |
| 查看可运行的单元测试断言 | `tests/maintained/` |
