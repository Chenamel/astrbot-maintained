# 工具权限单一入口（P6 处置 · T8-05）

> **目标语义（负责人 2026-10-12 拍板）**：**A —— 只统一入口与命名，判定强度逐点保持现状**。
> ⇒ 本次改动的验收标准是**行为零变化**，唯一产出是"权限判定只有一个实现"。
> **明确不做**：把两种判定合并成 AND。理由见 §2。

## 1. P6 问题：两套权限模型并存

| 模型 | 入口 | 判据 | 现网调点 |
|---|---|---|---|
| **身份模型** | `check_admin_permission` | 配置 `computer_use_require_admin`（默认 True）+ `event.role != "admin"` | **11 处**：`cua.py` ×3、`fs.py` ×2、`shipyard_neo/browser.py` ×3、`shipyard_neo/neo_skills.py` ×2、`message_tools.py` ×1 |
| **意图模型** | `check_execution_permission`（本 fork 新增） | `execution_denial()` 判定"当前消息是否授权执行" | **4 处**：`python.py` ×2、`shell.py` ×2 |

两者都在 `astrbot/core/tools/computer_tools/util.py`，互不引用。表现为"权限强度不一致"：
`fs.py` 只看身份不看意图，`python.py` / `shell.py` 只看意图不看身份。

## 2. 为什么选 A，而不是 B / C

| 候选 | 内容 | 结论 |
|---|---|---|
| **A 仅统一入口/命名** | 单一入口 + 显式级别参数，**强度逐点不变** | ✅ **采用** |
| B 统一到最强（AND） | 15 处全部同时过"身份 + 意图" | ❌ 会把 `execution_denial` 的**已知误判**推广到 11 个原本不看意图的调点 —— 直接违反「原版插件 100% 兼容 > fork 优化」。且 T8-10 尚未修复，等于先扩散再修补 |
| C 入口 + 强度参数 + 预留 `both` 组合 | 比 A 多一个组合级别 | ❌ 本次不做。组合级别是未来 T8-10 修好以后再评估的事，现在留出开关就是留出错用的口子 |

**关于 T8-10**：`execution_denial` 的误判矩阵已钉死在
`docs/maintained/code-delivery-policy.md` 与对应测试里。
本次**不修改**其任何判定逻辑，也不扩大它的适用范围。

## 3. 为什么那 5 个干净的上游调点文件不动

`cua.py` / `fs.py` / `shipyard_neo/browser.py` / `shipyard_neo/neo_skills.py` / `message_tools.py`
继续调用 `check_admin_permission`，原因有三条硬约束：

1. **它是上游符号且在该包的 `__all__` 里导出** —— `astrbot/core/tools/computer_tools/__init__.py`
   明确 import 并列 `check_admin_permission`。按兼容边界「冻结」条款不能删。
2. **上游测试依赖这个名字做 monkeypatch** —— `tests/unit/test_cua_computer_use.py`
   用 `monkeypatch.setattr(cua_tools, "check_admin_permission", lambda *args: "denied")`
   验证"鉴权失败后不得继续 GUI 查询"。一旦 `cua.py` 改调别的名字，桩失效、断言失败，
   直接打破红线「上游 `295 passed + 17 xfailed` 不变」。
3. **零冲突原则（底线 4）** —— 这 5 个文件未被登记为 core 补丁；改它们就要进台账（36 → 41），
   为本不需要的收益无谓扩大 fork 足迹。

⇒ 最终形态：`check_admin_permission` 成为**单一入口在身份级别上的转发器**（无自己的判定逻辑），
5 个干净文件的**调用拼写不变、行为不变**，而**实现只剩一处**。

## 4. 契约（`astrbot/core/tools/computer_tools/util.py`）

```python
class ToolPermissionLevel(enum.Enum):
    IDENTITY = "identity"    # 管理员身份
    EXECUTION = "execution"  # 当前消息执行授权

def check_tool_permission(
    context: ContextWrapper[AstrAgentContext],
    operation_name: str,
    level: ToolPermissionLevel,
) -> str | None: ...
```

- **返回值**：放行返回 `None`；拒绝返回可直接交给调用方返回的错误串（沿用现状，不改文案）。
- **无默认级别**：调用方必须显式声明，避免"忘了传就用默认"造成强度漂移。
- **`check_admin_permission(context, operation_name)`**：保留的上游符号，
  等价于 `check_tool_permission(..., ToolPermissionLevel.IDENTITY)`，**自身不含判定逻辑**。
- **`check_execution_permission`**：本 fork 私有符号，无外部引用，**已删除**；
  `python.py` / `shell.py` 改为调用单一入口的 `EXECUTION` 级。

### 逐点强度映射（与改动前**逐点等价**）

| 文件 | 调点 | 级别 | 变化 |
|---|---|---|---|
| `python.py` ×2 | Python execution | `EXECUTION` | 仅换写法 |
| `shell.py` ×2 | Shell execution / Shell session management | `EXECUTION` | 仅换写法 |
| `cua.py` ×3 | Taking CUA screenshots / Using CUA mouse / Using CUA keyboard | `IDENTITY` | **不动**（上游干净文件 + 测试依赖） |
| `fs.py` ×2 | File upload/download | `IDENTITY` | **不动** |
| `shipyard_neo/browser.py` ×3 | Using browser tools | `IDENTITY` | **不动** |
| `shipyard_neo/neo_skills.py` ×2 | Using skill lifecycle tools | `IDENTITY` | **不动** |
| `message_tools.py` ×1 | 消息工具 | `IDENTITY` | **不动** |

## 5. 本次明确不做的事

- 不改任何判定的**强度**（不新增、不删减、不合并）
- 不把 `execution_denial` 用到任何新的调用点
- 不动 `astrbot/core/tools/computer_tools/__init__.py` 的 `__all__`
- 不新增或删除任何工具、配置项、钩子

## 6. 验证

`tests/maintained/test_tool_permission_entry.py`：钉住"两个级别各自的行为与改动前一致"、
"`check_admin_permission` 是转发器（无独立逻辑）"、"15 个调点的级别映射不漂移"。
