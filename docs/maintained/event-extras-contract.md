# 事件附加字段契约（R5）

> 目标：核心不再直接读写**插件私有**的事件附加字段，而是通过一个有名字、有类型、
> 有兜底的契约层。字面量保持原样，所以现存插件零改动。
>
> 编写时间：2026-11-04 · 对应风险 R5 / 病根 C3

---

## 1. 问题

`astrbot/core/**` 里有 **9 个键、16 处**读取形如 `event.get_extra("_enhance_xxx")`：

| 键 | 方向 | 处数 |
|---|---|---|
| `_enhance_active_reply_token` | 插件写 → core 读 | 4 |
| `_enhance_visual_unavailable` | core 读**并写** | 3 |
| `_enhance_owned_quote_image_urls` | 插件写 → core 读 | 2 |
| `_enhance_followup_direct` | 插件写 → core 读 | 2 |
| `_enhance_visual_requested` | 插件写 → core 读 | 1 |
| `_enhance_proactive_lightweight` | 插件写 → core 读 | 1 |
| `_enhance_owned_image_urls` | 插件写 → core 读 | 1 |
| `_enhance_followup_task` | 插件写 → core 读 | 1 |
| `_enhance_active_reply_triggered` | 插件写 → core 读 | 1 |

**为什么这是问题**，不是风格问题：

1. **核心反向依赖插件**。项目自己的 P2 原则是"core 不得反向硬依赖插件"，
   T8-03 已经把"按插件目录名"改成能力契约，这批 `_enhance_*` 是同一类问题的残留。
2. **字段名带 `_` 前缀，是私有的意思**。插件改名、换实现或卸载后，核心**静默走 false 分支**：
   图片丢失、followup 退化、主动回复判断反转，**全程无日志**。
3. **无类型约定**。`_enhance_owned_quote_image_urls` 被当作 `dict` 直接 `.get(...)`，
   `_enhance_owned_image_urls` 被当作 `list` 直接 `extend(...)`；
   插件若写成别的类型（例如 `None`、字符串），core **抛异常**而不是降级。

---

## 2. 为什么不能"顺手改个更好的名字"

这些键是**跨进程契约**：插件在跑，核心在读。改名的后果是现存插件全部失效，
且失效方式是"静默不生效"，不会有任何报错。因此本轮**只收紧读写方式，不改变字面量**。

字面量本身也是测试的一部分：`tests/` 里有 14 处直接用字面量构造事件，
它们保持原样，就是"字面量没变"的证明。

---

## 3. 方案

新增 `astrbot/api/event/extras.py` —— 注意**不能**放进 `astrbot/api/event/__init__.py`：
那个文件在上游基线里就存在，改动会违反 API 冻结（`test_api_frozen.py` 会红）。

### 3.1 三组内容

**① 键名常量**（唯一来源）

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

**② 带兜底的读取器**（类型不对时返回默认值，不抛异常）

| 函数 | 返回 | 兜底 |
|---|---|---|
| `active_reply_token(event)` | `str` | `""` |
| `is_active_reply(event)` | `bool` | `False` |
| `visual_requested(event)` | `bool` | `False` |
| `visual_unavailable(event)` | `bool` | `False` |
| `owned_image_urls(event)` | `list[str]` | `[]` |
| `owned_quote_image_urls(event)` | `dict[str, list[str]]` | `{}` |
| `followup_direct(event)` | `bool` | `False` |
| `followup_task(event)` | `str` | `""` |
| `proactive_lightweight(event)` | `bool` | `False` |
| `active_reply_triggered(event)` | `bool` | `False` |

**③ 唯一的写入器**：`set_visual_unavailable(event, flag)` —— 只有这一个键是 core 自己写的。

### 3.2 降级规则

- 事件没有 `get_extra` / `set_extra`（鸭子类型的测试替身）→ 返回默认值，不抛异常。
- `get_extra` 自身抛异常 → 返回默认值，**记一次 debug**。
- 值类型不符（例如 url 列表给了 `None` 或字符串）→ 返回默认值。
  字符串按"单个 url"接受，不拆字符 —— 那是最常见的插件笔误。

### 3.3 不改的部分

- 不改任何字面量（见 §2）。
- 不改插件的写入侧：插件继续 `set_extra("_enhance_xxx", ...)`，无需感知本模块。
- 不改 `_direct_turn_*` 系列：那是本 fork 自己的键，不属于插件私有契约。

---

## 4. 落点与改动清单

| 文件 | 改动 |
|---|---|
| `astrbot/api/event/extras.py` | **新增**：常量 + 10 个读取器 + 1 个写入器 |
| `astrbot/core/agent/runners/tool_loop_agent_runner.py` | 1 处改读取器 |
| `astrbot/core/astr_agent_run_util.py` | 1 处 |
| `astrbot/core/astr_main_agent.py` | 3 处（同一条件表达式） |
| `astrbot/core/code_delivery_policy.py` | 2 处 |
| `astrbot/core/pipeline/process_stage/follow_up.py` | 1 处 |
| `astrbot/core/pipeline/process_stage/method/agent_sub_stages/image_input.py` | 3 处（含 1 处写入） |
| `astrbot/core/utils/direct_turns.py` | 3 处 |
| `tests/maintained/test_api_frozen.py` | 允许清单加新文件 |
| `tests/maintained/test_event_extras.py` | **新增**：契约测试 |

---

## 5. 验收标准

1. `grep -r '_enhance_' astrbot/core` **归零**（常量只出现在 `api/event/extras.py`）。
2. `grep -r '_enhance_' astrbot/api/event/extras.py` 恰好 9 个键各一次。
3. 全部现存测试通过：维护版 568 → 只增不减；上游 2949 passed / 2 xfailed。
4. 新增测试覆盖：每条读取器的正常值、错误类型降级、事件无 extras 时不崩。
5. `release_gate.py` 全绿。
6. 实例启动无新增 ERROR，插件行为不变（图片/引用/主动回复路径各走一次现成测试）。

---

## 6. 遗留（本轮不做）

- **写入侧仍在插件里**。本轮只保证核心不"裸读"私有键，插件依旧直接 `set_extra`。
  把写入也收进 API 需要改第三方插件源码，超出本仓范围。
- **`_enhance_*` 前缀仍在**。改名需要插件与核心同时升级，属破坏性变更，
  应留到有版本协商机制之后（见方案 R14：双 schema 收敛那条线）。
- **没有运行期告警**。目前降级是静默的（debug 级）。若将来要"插件写错类型时提醒一次"，
  可在读取器里加一次性 warning，但那会改变日志噪声水平，先不做。
