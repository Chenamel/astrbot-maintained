# 插件作者 5 分钟入门

本 fork 的卖点是补了上游没有的底层 API。这一页带你写第一个能跑的插件，并说明这些 API
在**补丁缺席时**会怎样降级。[`api-contract.md`](./api-contract.md) 是唯一规格来源，
本文只做入口导航；安装与启动见 [`install.md`](./install.md)。

## 1. 最小可运行插件

新建目录 `data/plugins/hello_fork/`，放两个文件。

`metadata.yaml`：

```yaml
name: hello_fork
desc: 演示如何使用维护版 fork 的公开 API
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
        # turns.is_current: 本回合是否仍未回复（补丁缺席时 fail-open 返回 True）
        already = not turns.is_current(event)
        yield event.plain_result(
            f"API 就位={turns.available()}，本回合已回复={already}"
        )
        turns.mark_sent(event)
```

重载插件后，在聊天里发 `/forkhello`，会收到一行回执。
每个模块都有 `available() -> bool`；返回 `False` 表示对应 core 能力未就位，
此时该模块的其余函数按 [`api-contract.md`](./api-contract.md) 的「补丁缺席时」列降级，**不会抛异常**。

> **唯一硬规则**：外部代码只允许 `import astrbot.api.*`。直接 import `astrbot.core.**`
> 私有路径的插件，会在上游 core 覆盖补丁时因顶层 `ImportError` 整体无法加载。

## 2. 用上 fork 的核心能力：人格感知生成

上游的 `Context.llm_generate()` / `Context.tool_loop_agent()` 直接调 provider，
跳过了 `on_llm_request` 钩子，而人格、长期记忆、群上下文插件正是挂在这个钩子上。
`generate_with_persona` 构造 `ProviderRequest` → 跑该钩子 → 再调 provider。
把 §1 的 `main.py` 换成下面这一版（或把 `say` 方法加进同一个类）：

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

`generate_with_persona(context, event, prompt, system_prompt="", image_urls=None,
chat_provider_id=None, timeout=None)` 是协程，返回 `LLMResponse | None`。
它**只生成文本、不发送**：由插件决定要不要 `yield`。能力未就位时返回 `None`（fail-closed），
所以上面先查 `persona_available()` 再调用，并对 `None` 做了降级。

## 3. 模块速查

下表的模块都在 `astrbot/api/**`，导入方式统一为 `from astrbot.api import <模块>`。
`astrbot.api.event` / `platform` / `provider` / `star` 是上游已有的公开面，写法与官方一致。

| 模块 | 一行用途 | 最小调用 | 补丁缺席时 |
|---|---|---|---|
| `turns` | 合并同账号直发回合、标记本回合已回复 | `turns.is_current(event)`；`turns.mark_sent(event)` | `is_current` → `True`，`mark_sent` 为 no-op，合并值返回空 |
| `delivery` | 判定文本是否构成真实源码交付 | `delivery.has_code_delivery(text)` | `False`；`code_task_spec` → `None` |
| `permissions` | 管理员判定与执行授权拒绝原因 | `permissions.execution_denial(event, config)` | 回退为「仅管理员」判定，**不放行**；`is_admin` 始终可用 |
| `media` | 图片输入、图片描述与防幻觉常量 | `media.has_visual_input(request)` | 常量使用与 core 同值的本地镜像；判定按请求字段工作 |
| `content` | 文本 / 图片内容部件的类型与判定 | `content.is_text_part(part)` | 部件类型解析为 `None`，判定返回 `False` |
| `runtime` | 数据目录、图片下载、本地时间、钩子时序模式 | `runtime.hook_timing_mode()` | 模式回落 `"legacy"`；下载类工具响亮失败 |
| `embedding` | 嵌入 provider 的类型判定 | `embedding.is_embedding_provider(obj)` | `False` |
| `proactive` | 轻量主动标记、人格生成、历史写回 | `proactive.proactive_switch_is_disabled()` | 开关恒 `True`；轻量判定 `False`；生成 `None`；写回 `False` |

每个模块的完整符号表、参数与返回值语义见 [`api-contract.md`](./api-contract.md) §3，
每个模块都有 `available() -> bool`。

## 4. 降级行为（本 fork 的设计特色）

所有新增模块经内部桥 `astrbot/api/_bridge.py`（**非公开面，插件不许 import**）的
`resolve(module, name, default)` 惰性解析 core 符号：模块或属性不存在时返回声明好的安全
默认值，且只在首次缺失时记一条日志。**不会抛 ImportError**，因此上游 core 覆盖补丁后
插件仍能导入、仍能启动。

- **安全相关一律 fail-closed**：`execution_denial` 缺席时回退「仅管理员」；
  `is_lightweight_proactive` 返回 `False`；`generate_with_persona` 返回 `None`。
- **非安全类保持旧行为**：`turns.is_current` 返回 `True`（无回合概念＝永远当前），
  `mark_sent` 为 no-op，`reset*` 返回 `False`。
- `permissions.execution_denial` 返回 `None` **不构成授权**，调用方仍须执行自己的权限闸门；
  只对 `None` / 非 `None` 做判断，不要对拒绝文本做等值断言。

## 5. 能力自检

不确定补丁是否就位时，先查能力位再决定路径：

```python
from astrbot.api import delivery, permissions, proactive, turns

print({
    "turns": turns.available(),
    "delivery": delivery.available(),
    "permissions": permissions.available(),
    "proactive": proactive.available(),
})
```

`False` 不代表插件写错了，只表示对应 core 补丁未就位，按 §3 的降级列处理即可。

## 6. 下一步读什么

| 想做的事 | 文档 |
|---|---|
| 查某个符号的准确签名与降级值 | [`api-contract.md`](./api-contract.md) |
| 了解事件附加字段、工具能力声明、权限单一入口 | `event-extras-contract.md`、`tool-capability-declaration.md`、`tool-permission-entry.md` |
| 理解这个 fork 相对上游的差异 | [`fork-advantages.md`](./fork-advantages.md) |
| 安装、启动、确认跑的是本 fork | [`install.md`](./install.md) |
| 看每个能力的可运行断言（可当示例读） | `tests/maintained/` |
