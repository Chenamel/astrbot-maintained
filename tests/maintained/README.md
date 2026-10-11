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

两种方式结果一致（均 **303** 项通过 + 1 项 skip）。方式 B 不需要额外磁盘，依赖实例 venv 存在。

> 另有 **1 项** `test_every_deviation_was_matched_when_upstream_runs` 只在**同时收集到上游那两个
> 测试文件**时才有意义（断言 17 条 xfail 全部命中），单独跑本目录时会 `skip`——属预期行为。

**为什么不用实例 venv 直接跑**：实例 venv 内**不允许安装**任何包（会污染运行环境）；
上游 `tests/conftest.py` 又需要 `pytest-asyncio`，故必须有独立环境。

> 运行方式没有额外的包装脚本：直接用上面的命令即可，
> 实例侧的漂移检测与恢复工具见 [`../../docs/maintained/tools.md`](../../docs/maintained/tools.md)。

## 现阶段测试清单（22 个文件 / 304 项）

| 文件 | 覆盖 |
|---|---|
| `test_api_surface.py` | 八个模块可导入、`__all__` 与契约一致、`_bridge` 不外露、能力清单键齐全、`resolve` 默认值语义 |
| `test_api_media.py` | 契约常量非空且 `NOTICE` 含 `MESSAGE`；`IMAGE_CAPTION_MARKER`；视觉输入/描述判定；显式 flag 优先 |
| `test_api_turns.py` | `is_current` fail-open 且不抛；`mark_sent` 安全；`merged_*` 读取与类型过滤；`reset*` 缺席返回 False |
| `test_api_delivery.py` | `CODE_DELIVERY_FAILURE` 非空；`code_task_spec` / `has_code_delivery` 缺席时返回安全默认值 |
| `test_api_permissions.py` | `is_admin` 多维判定；**非管理员恒被拒绝**（安全不变量）；`execution_denial` 不抛 |
| `test_api_proactive.py` | 开关恒为关闭；模块**不存在任何 enable 入口**；分类器 fail-closed |
| `test_api_content.py` | `is_text_part` / `is_image_part` 缺席与容错；OpenAI 风格 dict 识别 |
| `test_api_runtime.py` | 数据目录为绝对路径；缺席时下载响亮失败、引用图返回空表 |
| `test_api_embedding.py` | `is_embedding_provider` 缺席与容错 |
| `test_manifest_guard.py` | 仓工作树↔台账自洽；台账只含 core；`proactive_must_remain_disabled`；条数钉 |
| `test_p11_deviations.py` | P11 注册表守护：α 9 / β 8 条数、nodeid 仍指向真实上游用例、理由含组别、β 红线文档与 core 锚点仍在、命中数 17/17 |
| `test_hook_timing_mode.py` | `hook_timing_mode` 双模式时序：legacy 下 yield 时 `on_agent_done` **未**触发（＝上游）、enhanced 下**已**触发（＝本 fork），并确认钩子最终都跑过 |
| `test_hook_timing_passthrough.py` | cron 与后台任务唤醒路径也读 `misc`：`hook_timing_mode` / `tool_schema_mode` 随配置生效，非法值回落默认 |
| `test_code_delivery_policy.py` | P10 手写正则的**当前实测行为**钉死：执行授权矩阵、拒答识别（含漏判/误报，标注 T8-10 待修）、源码任务与交付判定 |
| `test_plugin_capability_lookup.py` | P2 能力契约发现：按能力方法名找插件（找不到/未激活/抛异常一律 fail-closed）、收尾只跑一次；**core 零插件目录名守卫**（白名单为空） |
| `test_tool_capability_declaration.py` | P3 工具能力自声明：执行类声明者未授权即移除（含「名字不在任何名单里」的反回归断言）、轻量主动＝声明或配置名单、默认名单兜底、persona 权限仍收窄、旧硬编码名单不许复活 |
| `test_tool_permission_entry.py` | P6 权限单一入口：身份/意图两级别各自的行为、**级别互不叠加**、`check_admin_permission` 无自有逻辑、旧并行入口已消失、15 个调点的级别映射不漂移 |
| `test_maintenance_gate.py` | P9 本地维护保护闸门：名单缺失**必告警**后放行、命中插件名/目录名拒绝、五种损坏形态 **fail-closed**、卸载两入口默认被拦且 `force=True` 可绕过 |
| `test_api_frozen.py` | 上游 api 相对 `baseline/v4.28.2` 零改动（白名单=9 新增文件） |
| `test_tools_check_drift.py` | 漂移检测：ok/mismatch/missing、退出码、JSON 输出、路径解析 |
| `test_tools_apply_patches.py` | 源校验中止、预演不写、备份收据、写回后复核、端到端修复 |

## 与仓库根 `conftest.py` 的关系

上游有 **17 项**测试本 fork **有意**不通过（P11，见 `docs/maintained/inventory.md` §4）。
按零冲突原则**上游测试文件一字未改**，改由仓库根 `conftest.py` 在收集阶段按
`maintained/p11_deviations.py` 的注册表打上 `xfail(strict=True)`：

- 失败 → `xfailed`（绿）；**意外通过 → `XPASS(strict)` 判红**（＝偏离被回退 / 被上游合并覆盖，报警）。
- 所以"全绿"的完整口径是：本目录全绿 **且** 上游那两个文件输出 `170 passed, 17 xfailed`。

```bash
"$TV" -m pytest tests/maintained -q
"$TV" -m pytest tests/unit/test_astr_main_agent.py tests/test_tool_loop_agent_runner.py -q
```

## 断言约定

补丁缺席时（当前基线）与补丁就位时（阶段 4 恢复后）**同一份测试都要通过**。因此凡是
依赖核心能力的断言都写成"相对 `available()` 判断"，而不是硬编码 `False`/`None`。
真正硬编码的只有两类：**契约常量** 与 **安全不变量**（例如"非管理员恒被拒绝"）。
