# tests/maintained/ — 本 fork 的测试

覆盖对象：`astrbot/api/**` 新增模块（阶段 3 起），以及后续 core 补丁。

## 为什么单独放在这里

- 上游 `tests/` 会被 `ruff` 排除（`[tool.ruff] exclude`），且随上游演进；本目录是**本 fork 自有**，遵循零冲突原则（新增路径）。
- 本目录的测试**不依赖运行中的 AstrBot**，也不连数据库 / 网络：用 `SimpleNamespace` 伪造 event / request / part。

## 如何运行

### 方式 A（推荐）：专用测试 venv

本机已建好一个**独立**测试环境（Python 3.12.13，与运行环境同版本；含 AstrBot 全部运行依赖 + pytest + pytest-asyncio）：

```bash
cd /d/asbot_core_for_fork
"C:/Users/philia093/.workbuddy/binaries/python/envs/astrbot-test/Scripts/python.exe" -m pytest tests/maintained -q
```

它既不是运行环境（不动实例 venv），也不是工具 venv（ruff 所在），互不污染。

### 方式 B（备用）：借包给实例 venv

```bash
IV="<AstrBot 实例>/venv/Scripts/python.exe"          # 提供运行依赖
EV="<托管工具 venv>"                                  # 提供 pytest / pytest-asyncio
PYTHONPATH="$EV/Lib/site-packages" "$IV" -m pytest tests/maintained -q
```

两种方式结果一致（均 47 项通过）。方式 B 不需要额外磁盘，依赖实例 venv 存在。

**为什么不用实例 venv 直接跑**：实例 venv 内**不允许安装**任何包（会污染运行环境）；
上游 `tests/conftest.py` 又需要 `pytest-asyncio`，故必须有独立环境。

阶段 6 会把运行方式固化成 `maintained/tools/` 里的一个脚本。

## 现阶段测试清单

| 文件 | 覆盖 |
|---|---|
| `test_api_surface.py` | 五模块可导入、`__all__` 与契约一致、`_bridge` 不外露、能力清单键齐全、`resolve` 默认值语义 |
| `test_api_media.py` | 契约常量非空且 `NOTICE` 含 `MESSAGE`；`IMAGE_CAPTION_MARKER`；视觉输入/描述判定；显式 flag 优先 |
| `test_api_turns.py` | `is_current` fail-open 且不抛；`mark_sent` 安全；`merged_*` 读取与类型过滤；`reset*` 缺席返回 False |
| `test_api_delivery.py` | `CODE_DELIVERY_FAILURE` 非空；`code_task_spec` / `has_code_delivery` 缺席时返回安全默认值 |
| `test_api_permissions.py` | `is_admin` 多维判定；**非管理员恒被拒绝**（安全不变量）；`execution_denial` 不抛 |
| `test_api_proactive.py` | 开关恒为关闭；模块**不存在任何 enable 入口**；分类器 fail-closed |

## 断言约定

补丁缺席时（当前基线）与补丁就位时（阶段 4 恢复后）**同一份测试都要通过**。因此凡是
依赖核心能力的断言都写成"相对 `available()` 判断"，而不是硬编码 `False`/`None`。
真正硬编码的只有两类：**契约常量** 与 **安全不变量**（例如"非管理员恒被拒绝"）。
