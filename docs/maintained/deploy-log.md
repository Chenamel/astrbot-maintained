# 部署台账（实例侧操作记录）

记录**对本机 AstrBot 实例**做过的写操作：何时、改了什么、如何回滚、验证结果。
仓库侧变更见 [`../../CHANGELOG.md`](../../CHANGELOG.md)；本文件只记实例侧动作。

---

## 2026-10-09 · 阶段 4 止血：恢复 26 个 core 补丁 + 部署 `astrbot/api` 层

**背景**：10-08 实例 core 被官方 v4.28.2 覆盖，26 个维护补丁全部丢失，
参考插件因顶层 `from astrbot.core.provider.entities import IMAGE_INPUT_UNAVAILABLE_NOTICE`
抛 `ImportError` 而整体无法加载（日志见 `<INST>/astrbot_manual.out.log` 10-08 22:43）。

**操作前状态**（实测）：

| 项 | 值 |
|---|---|
| 实例 core 版本 | 4.28.2（10-08 22:43 日志中运行的却是 v4.29.0-beta.1，随后被换回 4.28.2） |
| 进程 | **无 AstrBot 进程运行**，6185 / 6199 未监听 |
| 台账 28 条 | 一致 0 / 缺失 9 / 内容不符 19 |

**备份**：`<INST>/optimization_backups/20261009_124413_CST_premaintenance/`（16 MB）

```
manifest.json    # 28 个目标文件的操作前状态（present/absent）+ 字节数 + SHA-256
core/            # 19 个「操作前存在」的原文件，按原相对路径存放
astrbot_full/    # 操作前 core/astrbot/ 整树副本（920 文件）
RESTORE.md       # 选择性回滚说明
```

> 注：`data/`（1.8 GB 运行数据）**未被本操作触碰**，故未备份。

**恢复内容**（`28 = 22 个 core 补丁 + 6 个 astrbot/api 新文件`）：

- 覆盖 19 个：`tool_loop_agent_runner.py`、`astr_main_agent.py`、`astr_agent_run_util.py`、
  `provider/entities.py`、`provider/sources/openai_source.py`、`pipeline/*` 6 处、
  `platform/sources/aiocqhttp/aiocqhttp_message_event.py`、`star/star_manager.py`、`star/updater.py`、
  `tools/computer_tools/{util,shell,python}.py`、`dashboard/services/plugin_service.py`
- 新增 9 个：`core/utils/direct_turns.py`、`core/code_delivery_policy.py`、`core/star/maintenance.py`、
  `api/_bridge.py`、`api/{media,turns,delivery,permissions,proactive}/__init__.py`

**来源**：补丁来自归档仓 `<INST>/maintenance_repos/astrbot_local/maintained_source/core`；
`astrbot/api/**` 的 6 个新文件来自本仓库 `D:/asbot_core_for_fork`。

**验证结果**：

| 检查 | 结果 |
|---|---|
| 台账 SHA-256（28 条，对实例 core 实测） | **28/28 一致，0 不符** |
| `astrbot.core.utils.direct_turns.coordinator` 导入 | ✅ `DirectTurnCoordinator` |
| `IMPORT_FAILURE 根因`（插件第 28 行 import） | ✅ 现已可解析 |
| `astrbot.api._bridge.capabilities()` | ✅ 5 项全 `True` |
| 机器人运行 | ⏳ **未启动**（操作前即未运行；需人工启动后验证插件加载） |

**遗留风险**：

1. ⚠️ **铁律 6 冲突**：`data/config/astrbot_plugin_astrbot_enhance_mode_config.json`
   的 `active_reply.enable` 曾为 **`true`**，该文件 mtime 为 10-08 23:45（晚于 core 被覆盖的 23:42），
   **非止血操作所致**。

**验证结果（机器人启动后补记）**：

| 检查 | 结果 |
|---|---|
| 机器人进程 | ✅ PID 211524，监听 `0.0.0.0:6199`（OneBot）、`127.0.0.1:6185`（面板） |
| **插件加载成功** | ✅ 监听 `127.0.0.1:6196` = 该插件的 `memory_rag_webui.port`，**插件本体已运行** |
| 启动时间旁证 | `data/plugins.json` 时间戳 `2026-10-09T14:12:20`；`data/temp/` 有 13:44 的媒体文件 |

> 探测注记：本机 PowerShell 的 `Get-Process` / `Get-CimInstance` 在沙箱下**静默返回空**，
> 曾据此误判"机器人未运行"。**进程与端口探测一律用 `netstat -ano` 交叉验证**。

---

## 2026-10-09 · 主动回复开关关闭（防调试期误发）

**原因**：机器人恢复运行后，`active_reply.enable = true` 会让主动回复真实生效；
调试阶段存在误发风险（可能被群管理员踢出机器人）。用户要求关闭。

**操作**：

| 项 | 值 |
|---|---|
| 目标文件 | `<INST>/core/data/config/astrbot_plugin_astrbot_enhance_mode_config.json` |
| 变更 | `active_reply.enable`: `true` → `false`（BOM 保留，其余 22 个字段与 8 个顶层键不变） |
| 备份 | `<INST>/optimization_backups/20261009_142013_CST_proactive_off/` |

**未改动**：`active_reply.batch_enable`（仍为 `true`）——它与主动回复开关是否独立，待用户确认。

**待确认（重要）**：插件进程正在运行，AstrBot 的插件配置在启动时载入内存。
**仅改磁盘文件可能不会即时生效**，且插件/机器人下次停止或保存配置时，
内存中的旧值（`enable=true`）**可能回写覆盖本次修改**。需要在面板插件配置页关闭开关，
或重启机器人，改后应复查文件值。

### 重启后复核（已排除上述风险）

用户重启机器人后实测：

| 检查 | 结果 |
|---|---|
| 进程 | 新 PID **207472**（重启前 211524）→ 确为重启 |
| 监听端口 | `6199` / `6185` / `6196` 全部在听 → **插件再次加载成功** |
| 配置文件 | `active_reply.enable = **False**`（保留）；mtime 仍为 14:20 = 本次修改时间，**未被重启重写** |
| 语义比对（当前文件 vs 改前快照） | **差异项 1 个**：`active_reply.enable` `True → False`；其余 21 个字段逐项一致 |
| 台账 28 条 | **28/28 一致** → 重启未触碰 core |

**结论**：AstrBot 启动时确实从磁盘重读插件配置，本次关闭**已真实生效**且不会被回写覆盖。
`active_reply.batch_enable` 经用户确认与主开关联动，无需单独处理。

**阶段 4 至此完成**：止血 + 运行验证 + 铁律 6 恢复（主动回复关闭）全部落地。


## 其它遗留项

2. ⚠️ **R3（启动器覆盖）**：10-08 的故障正是 core 被覆盖引起。启动器内**不要点「更新核心」**，
   否则本次恢复会被再次覆盖。阶段 6 的 `check_drift` 会提供一键检测与重打。
3. 阶段 5 仍需把插件那 3 处私有 import 改为 `astrbot.api.*` + 软依赖，
   否则每次 core 漂移仍会让插件整体下线（本次只是恢复了现状，未消除根因）。

---

## 2026-10-09 · 阶段 5 插件正规化（消除 core 漂移根因）

**目标**：把插件对 core 的 8 处私有依赖全部收敛到 `astrbot.api.*`，并加降级兜底，
使 core 再次漂移时插件**仍能加载**（功能降级）而不是整体下线。

**先做核实（决定改动面）**：扫描全实例 14 个有 `astrbot.core` import 的插件，
确认**只有 `astrbot_plugin_astrbot_enhance_mode/main.py` 一个生产文件**引用了补丁私有符号；无人引用
`code_delivery_policy` / `IMAGE_INPUT_UNAVAILABLE_MESSAGE`。

**A. api 层扩建（公开仓，3 个新模块，仍为纯新增）**

| 模块 | 暴露 |
|---|---|
| `astrbot/api/content/` | `TextPart`、`ImageURLPart`、`is_text_part`、`is_image_part` |
| `astrbot/api/runtime/` | `get_astrbot_data_path`、`download_image_by_url`、`extract_quoted_message_images` |
| `astrbot/api/embedding/` | `EmbeddingProvider`、`is_embedding_provider` |

- 类型在 core 缺席时为 `None`，并提供 `is_*` 辅助函数（避免 `isinstance(x, None)` 抛错）；
- 下载类函数**失败要响**（`RuntimeError`），路径/引用图**降级为可用默认值**；
- 台账 28 → **31 条**；fork 仓测试 47 → **62 项**全绿；`ruff` 干净。

**B. 插件改造（私有仓 extras）**

- 6 处顶层 core import → `astrbot.api.{content,media,runtime,embedding,turns}`，
  整体包在 `try/except ImportError` 中，缺席时记 `warning` 并以降级实现继续；
- `isinstance(part, TextPart)` → `is_text_part(part)`（4 处）；
  `isinstance(provider, EmbeddingProvider)` → `is_embedding_provider(...)`；
  注解 `-> EmbeddingProvider | None` 改为字符串注解（该文件无 `from __future__ import annotations`，
  求值时会踩到 `None | None`）；
- `TextPart(...)` 构造统一走 `_make_text_part()`，类型缺席时返回 `None` 并跳过；
- 2 处函数内 `from astrbot.core.utils.direct_turns import coordinator` → 顶层
  `astrbot.api.turns.reset / reset_all`；
- 插件 `main.py` 现在 **`astrbot.core` 零引用**。
- `tests/test_visual_context.py`：`TextPart`/`IMAGE_INPUT_UNAVAILABLE_NOTICE`/`ProviderRequest`
  改走公开面；**保留 2 处刻意引用 core 内部**（provider source 实现、`DirectTurn`/`DirectTurnCoordinator`），
  已加注释说明原因（api 层有意不暴露内部数据模型）。

**验证**

| 检查 | 结果 |
|---|---|
| 插件自带测试（用**已打补丁的实例 core**） | **183 passed** |
| 插件 `main.py` 语法编译 | ✅ |
| api 层部署后台账 | **31/31 一致** |
| 仓 → 实例同步 | 字节一致；改前哈希 `50dd1aaf…`（与归档台账一致，可精确回滚） |

**保护机制**：`data/optimization_tracking/maintenance_registry.json` 的 `protected_plugins`
**已含该插件**，面板「更新插件」会被 `maintenance.py` 拦截，不会覆盖本次改造
（该名单同时印证 `proactive_must_remain_disabled: true`）。

**待完成**：插件仍运行着旧代码，需要在面板重载该插件（或重启机器人）后复核（T5-07）。

