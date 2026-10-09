# tests/maintained/ — 本 fork 的测试

覆盖对象：`astrbot/api/**` 新增模块（阶段 3 起），以及后续 core 补丁。

## 为什么单独放在这里

- 上游 `tests/` 会被 `ruff` 排除（`[tool.ruff] exclude`），且随上游演进；本目录是**本 fork 自有**，遵循零冲突原则（新增路径）。
- 本目录的测试**不依赖运行中的 AstrBot**，也不连数据库 / 网络：用 `SimpleNamespace` 伪造 event / request / part。

## 如何运行

需要一个**既有 AstrBot 运行时依赖**、又有 **pytest** 的解释器。本机实测可行的组合是
「实例 venv 的 python + 托管工具 venv 的 pytest」：

```bash
IV="<AstrBot 实例>/venv/Scripts/python.exe"          # 提供运行依赖（deprecated/aiohttp/...）
EV="<托管工具 venv>"                                  # 提供 pytest / pytest-asyncio

cd <本仓库根>
PYTHONPATH="$EV/Lib/site-packages" "$IV" -m pytest tests/maintained -q
```

Windows + Git Bash 示例（本机实际值）：

```bash
cd /d/asbot_core_for_fork
PYTHONPATH="C:/Users/philia093/.workbuddy/binaries/python/envs/default/Lib/site-packages" \
"C:/Users/philia093/.astrbot_launcher/instances/83ca721d-26d2-4dd0-9932-ef9299d8829d/venv/Scripts/python.exe" \
-m pytest tests/maintained -q
```

**为什么这样组合**：上游 `tests/conftest.py` 需要 `pytest-asyncio`；而实例 venv 内**不允许安装**任何包
（会污染运行环境），托管 venv 又缺少 AstrBot 的第三方依赖。用 `PYTHONPATH` 把纯 Python 的 pytest
借给实例解释器是零污染的做法。

阶段 6 会把它固化成 `maintained/tools/` 里的一个可复现脚本；届时若需要隔离环境，可另建专用测试 venv。

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
