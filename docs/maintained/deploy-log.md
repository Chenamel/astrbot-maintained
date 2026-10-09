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

1. ⚠️ **铁律 6 冲突（未处理，待用户决定）**：`data/config/astrbot_plugin_astrbot_enhance_mode_config.json`
   的 `active_reply.enable` 当前为 **`true`**，而 `installed_manifest.json` 明载
   `proactive_must_remain_disabled = true`。该文件 mtime 为 10-08 23:45（晚于 core 被覆盖的 23:42），
   **非本次操作所致**。插件一旦加载成功，主动回复即会生效——与铁律 6 冲突。
2. ⚠️ **R3（启动器覆盖）**：10-08 的故障正是 core 被覆盖引起。启动器内**不要点「更新核心」**，
   否则本次恢复会被再次覆盖。阶段 6 的 `check_drift` 会提供一键检测与重打。
3. 阶段 5 仍需把插件那 3 处私有 import 改为 `astrbot.api.*` + 软依赖，
   否则每次 core 漂移仍会让插件整体下线（本次只是恢复了现状，未消除根因）。
