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

### 决策确认（用户）

| 问题 | 决定 |
|---|---|
| 阶段 5 改造范围 | **8 处全收敛**（保持现状）。理由：铁律 1 明文"外部只允许 import `astrbot.api.*`"，且这是"最接近公共插件调用"的形态 |
| 插件自带 tests | **保持现状**（能走公开面的已改；2 处刻意保留 core 内部引用并加注释） |

> 诚实前提：`TextPart` / `EmbeddingProvider` / `get_astrbot_data_path` / `download_image_by_url` /
> `extract_quoted_message_images` 在**官方公开面并不存在**，官方生态的普通插件本来 import 不到；
> 是本 fork 把它们补进公开面，插件才做到"只 import `astrbot.api.*`"。
> 真正的"最公共"是插件不依赖这些符号——那属插件重写，不在本次范围。

### 当前状态（待用户重载）

| 检查 | 结果 |
|---|---|
| 实例 `main.py` 哈希 | `ed34c248…` = 改造后版本（15:38 同步） |
| 插件 `__pycache__/main.cpython-312.pyc` | **10-08 23:48**，早于 `main.py` → **尚未重载** |
| 机器人进程 | PID 207472（未变），仍持有旧代码 |

⇒ **下一步动作：在面板「插件」页重载该插件**（或重启机器人），随后复核端口 6196 与日志。

### 重启后复核（T5-07 通过）

用户直接整机重启 AstrBot，复核结果：

| 检查 | 结果 |
|---|---|
| 进程 | 新 PID **200188**（重启前 207472）→ 确为重启 |
| 监听端口 | `6199` / `6185` / **`6196`（插件 WebUI）** 全在听 → **插件加载成功** |
| 插件字节码 | `main.cpython-312.pyc` mtime **15:54** > `main.py` 的 **15:38** → **新代码已编译并加载** |
| 重新编译的 pyc 数 | 2 个（>15:40） |
| `plugins.json` | 15:54（启动痕迹） |
| `active_reply.enable` | 仍为 **`False`**（重启未回写） |
| 台账 | **31/31 一致**（重启未触碰 core） |

**阶段 5 结论**：插件已彻底摆脱对 `astrbot.core` 的依赖（`main.py` 零 core 引用），
并具备降级能力——core 再次被官方覆盖时，插件仍能加载（功能降级）而不是整体下线。
**"core 一动插件全死"这一立项根因已消除。**

---

## 2026-10-09 · 阶段回顾审计（阶段 1–5）与两项修复

按用户要求对前五阶段做逐项复核。**全部通过项**：台账 31/31、既有 api 文件零改动、
CRLF 0、文档 18 篇无断链、`ruff` 干净、fork 测试 62 项通过、extras 仓 33 文件无 `data/`+`__pycache__`。

### 修复 1（P0）· 维护版 core 未进 fork 仓 —— 单一真相源缺口

**发现**：fork 仓内那 19 个 core 文件是**基线原样**（例：`provider/entities.py`
仓 `1d2f1c41…` vs 实例 `c66a4c78…`），3 个新增模块则完全不存在。
即 **22 个 core 补丁只存在于两处，且都在启动器管理的实例目录内**（归档仓 +
live core）。这既违反「单一真相源」，也与 `design.md §1`（维护分支应含已登记补丁）不符，
**正是当初事故的脆弱性来源**。

**修复**：按台账把 22 个文件从归档仓导入 fork 仓（源哈希先与台账逐条核对，不符即中止），
新增 3 / 覆盖 19，提交 `feat(core): import the maintained core patch set (22 files)`。
现 fork 仓即维护版 core 的真相源，`ruff` 与 62 项测试仍全绿。

### 修复 2（P1）· `astr_main_agent.py` 换行口径不一致

**发现**：31 条台账文件中**唯一一个** `astr_main_agent.py` 是 CRLF（1898 处），
且台账哈希按 **CRLF 口径**记录；而 `.gitattributes` 的 `* text=auto eol=lf` 会在
克隆时归一化为 LF → **新克隆出来后该文件哈希必然与台账不符**，漂移检测会永久误报。

**修复**：仓内与实例该文件统一归一化为 LF（CRLF 1898 → 0），台账哈希更新为 LF 口径
（`0ffb6fe27a8c…` → `83a1760ded1d…`）。**双端复核均 31/31 一致**。

> 附带教训：Windows 上 `pathlib.write_text` 会把 `\n` 写成 `\r\n`；
> 写 JSON/台账一律用 `write_bytes`（见 `project_rules.md` §8）。

### 明确的排除项（非疏漏）

**4 个 dashboard 前端补丁文件不进仓、不进台账**：

| 文件 | 现状 |
|---|---|
| `dashboard/src/components/chat/ThreadedMarkdownMessagePart.vue` | 实例与仓**哈希相同**（已回退到基线） |
| `.../message_list_comps/MarkdownMessagePart.vue` | 同上 |
| `dashboard/src/assets/mdi-subset/materialdesignicons-subset.css` | 同上 |
| `dashboard/src/utils/messageControlDisplay.js` | **仓内不存在**，实例残留孤儿文件（无任何文件引用它） |

即：**dashboard 前端补丁已在 10-08 那次覆盖中一并丢失**（3 个被回退、1 个成孤儿），
并非"未导入"。按 inventory §3.4 的分级（🔵 非 core 前端改线）与用户
「这是 core 的项目，只留 core 相关内容」的指示，**不恢复、不纳入台账**。
若日后要修复 WebUI 的 Satori 标签渲染，应作为独立任务从零实现。





---

## 2026-10-09 · 阶段 6 工具链（check_drift / apply_patches）

**产出**：`maintained/tools/{check_drift,apply_patches}.py` + `docs/maintained/tools.md` + 24 项测试。
工具**只碰台账内文件**，不含任何插件信息（与本仓「只留 core」定位一致）。

**端到端实测（真实实例）**：

| 步骤 | 结果 |
|---|---|
| `check_drift --check-repo` | 实例 31/31、仓内 31/31 → **NO DRIFT**，退出码 0 |
| 故意注入漂移（给 `direct_turns.py` 追加一行注释） | 检测到 `1 mismatch` → **DRIFT DETECTED**，退出码 1 |
| `apply_patches` 预演 | `nothing to do`（未注入时）/ 正确列出待改项，**不写文件** |
| `apply_patches --apply` | 自动备份 → 写回 → `verify: 31 entries -> 31 ok` |
| 修复后复核 | **NO DRIFT**；文件字节与注入前**完全一致** |
| 测试残留 | 已清理（该备份仅含注入漂移那份文件） |

**意义**：把「启动器覆盖 core」的处置从**人工排查半小时**压缩为**两条命令**（检测 + 一键重打）。
工具**不试图拦启动器**（拦不住），定位是事后快速检测与恢复。

---

## 2026-10-09 · 阶段 7 打磨成果部署（等待重启）

**部署内容**：C1–C4 的 12 个 core 文件（P4 常量下沉、P5 正式字段、P7 debug 日志、P8 具名常量）。

| 步骤 | 结果 |
|---|---|
| 全量质量门（部署前） | maintained **94 passed** / ruff `All checks passed` / 上游 **17 failed（= 基线，无新增）** / 插件 **188 passed** |
| `check_drift`（部署前） | 实例 `19 ok / 12 mismatch` → **DRIFT DETECTED**；仓内 `31/31` → NO DRIFT |
| `apply_patches` 预演 | 正确列出 12 个待更新文件，**未写任何东西** |
| `apply_patches --apply` | 备份 `<INST>/optimization_backups/20261009_201439_CST_apply_patches/` → 写回 → `verify: 31 -> 31 ok` |
| 部署后 `check_drift` | 实例 **31/31 NO DRIFT**；仓内 **31/31 NO DRIFT**（双端一致） |
| 插件同步 | `main.py` + `tests/test_api_status.py` 已同步到实例；删除残留 `main.cpython-313.pyc` |

**待用户实操**：

1. **重启 AstrBot**（当前 PID 200188），使 core 改动生效；
2. 面板**重载插件**，使 `enhance api-status` 与新代码生效。

**重启后只读复核清单**（无需 QQ 实测）：

```bash
netstat -ano | grep -E ":6185|:6199|:6196"                       # 三端口 LISTENING（PID 应变）
python maintained/tools/check_drift.py --instance <INST> --check-repo   # 双端 NO DRIFT
ls -la <INST>/core/astrbot/core/provider/__pycache__/entities.cpython-312.pyc   # pyc 应晚于部署时刻
```

**注记**：`.pytest_cache` 曾被误同步进实例插件目录，已删除并为 extras 仓补上忽略规则（提交 `f79a81a`）。

---

## 2026-10-09 · 阶段 7 打磨成果部署（等待重启）

**部署内容**：C1–C4 的 12 个 core 文件（P4 常量下沉、P5 正式字段、P7 debug 日志、P8 具名常量）。

| 步骤 | 结果 |
|---|---|
| 全量质量门（部署前） | maintained **94 passed** / ruff `All checks passed` / 上游 **17 failed（= 基线，无新增）** / 插件 **188 passed** |
| `check_drift`（部署前） | 实例 `19 ok / 12 mismatch` → **DRIFT DETECTED**；仓内 `31/31` → NO DRIFT |
| `apply_patches` 预演 | 正确列出 12 个待更新文件，**未写任何东西** |
| `apply_patches --apply` | 备份 `<INST>/optimization_backups/20261009_201439_CST_apply_patches/` → 写回 → `verify: 31 -> 31 ok` |
| 部署后 `check_drift` | 实例 **31/31 NO DRIFT**；仓内 **31/31 NO DRIFT**（双端一致） |
| 插件同步 | `main.py` + `tests/test_api_status.py` 已同步到实例；删除残留 `main.cpython-313.pyc` |

**待用户实操**：

1. **重启 AstrBot**（当前 PID 200188），使 core 改动生效；
2. 面板**重载插件**，使 `enhance api-status` 与新代码生效。

**重启后只读复核清单**（无需 QQ 实测）：

```bash
netstat -ano | grep -E ":6185|:6199|:6196"                       # 三端口 LISTENING（PID 应变）
python maintained/tools/check_drift.py --instance <INST> --check-repo   # 双端 NO DRIFT
ls -la <INST>/core/astrbot/core/provider/__pycache__/entities.cpython-312.pyc   # pyc 应晚于部署时刻
```

**注记**：`.pytest_cache` 曾被误同步进实例插件目录，已删除并为 extras 仓补上忽略规则（提交 `f79a81a`）。

### 重启后复核（T7-10 通过，2026-10-09 22:5x）

| 检查 | 结果 |
|---|---|
| 进程 | 新 PID **213812**（重启前 200188）→ 确为重启 |
| 监听端口 | `6199` / `6185` / `6196` 全在听 → 机器人 + 插件均正常 |
| core 新代码 | `entities` / `direct_turns` / `tool_loop_agent_runner` / `api/media` 的 pyc 均为 **22:49**（晚于 20:14 部署）→ **已编译加载** |
| 部署生效实证 | 在实例 core 中导入 `AUXILIARY_LLM_TIMEOUT_SEC=30`、`MAX_TURN_IMAGE_URLS=2`、`CHANGE_POLL_INTERVAL_SEC=0.25`、`IMAGE_CAPTION_MARKER='<image_caption>'` 全部成功 |
| 插件新代码 | `main.cpython-312.pyc` **22:49:38** > `main.py` 20:07 → 新代码已加载（其余 pyc 仍为 13:34，因源码未变，符合预期） |
| `check_drift` | 实例 **31/31 NO DRIFT**；仓内 **31/31 NO DRIFT** |
| 插件依赖面 | 实例 `main.py` 中 `astrbot.core` **0 处**；`enhance api-status` 命令**在**（1 处） |
| 铁律 ⑥ | `active_reply.enable = **False**`（重启未回写） |

**阶段 7 至此完成**：打磨（P4/P5/P7/P8）+ 回归护栏 + 文档对齐 + 插件清理与只读自检，
全部部署并重启验证通过。仅剩 QQ 侧 `enhance api-status` 冒烟（可选，随时可做）。

### 重启后复核（T7-10 通过，2026-10-09 22:5x）

| 检查 | 结果 |
|---|---|
| 进程 | 新 PID **213812**（重启前 200188）→ 确为重启 |
| 监听端口 | `6199` / `6185` / `6196` 全在听 → 机器人 + 插件均正常 |
| core 新代码 | `entities` / `direct_turns` / `tool_loop_agent_runner` / `api/media` 的 pyc 均为 **22:49**（晚于 20:14 部署）→ **已编译加载** |
| 部署生效实证 | 在实例 core 中导入 `AUXILIARY_LLM_TIMEOUT_SEC=30`、`MAX_TURN_IMAGE_URLS=2`、`CHANGE_POLL_INTERVAL_SEC=0.25`、`IMAGE_CAPTION_MARKER='<image_caption>'` 全部成功 |
| 插件新代码 | `main.cpython-312.pyc` **22:49:38** > `main.py` 20:07 → 新代码已加载（其余 pyc 仍为 13:34，因源码未变，符合预期） |
| `check_drift` | 实例 **31/31 NO DRIFT**；仓内 **31/31 NO DRIFT** |
| 插件依赖面 | 实例 `main.py` 中 `astrbot.core` **0 处**；`enhance api-status` 命令**在**（1 处） |
| 铁律 ⑥ | `active_reply.enable = **False**`（重启未回写） |

**阶段 7 至此完成**：打磨（P4/P5/P7/P8）+ 回归护栏 + 文档对齐 + 插件清理与只读自检，
全部部署并重启验证通过。仅剩 QQ 侧 `enhance api-status` 冒烟（可选，随时可做）。
