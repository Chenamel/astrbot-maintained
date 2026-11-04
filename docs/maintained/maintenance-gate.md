# 本地维护版保护闸门（P9 处置 · T8-06）

> 目标：**更新 / 覆盖安装 / 卸载**三个入口闸门齐备，且"名单不可读"这件事**可观测**。
> 决策时间：2026-10-12。

## 1. P9 问题

`astrbot/core/star/maintenance.py` 的 `assert_plugin_update_allowed`：

1. `maintenance_registry.json` **不存在 → 静默 `return`（fail-open，无任何日志）**；
2. 名单**损坏**（非法 JSON / 结构不对）→ 抛 `LocalMaintenanceProtectionError`（fail-closed，正确）；
3. `uninstall_plugin` / `uninstall_failed_plugin` **完全没有闸门** ⇒ 本地维护版可以被面板一键删掉。

## 2. 语义矩阵（处置后）

| 情形 | 行为 | 理由 |
|---|---|---|
| 名单文件**不存在** | **明确 `logger.warning`（含路径与原因）后放行** | 见 §3 |
| 名单**存在但不可读/结构非法** | **fail-closed**：抛 `LocalMaintenanceProtectionError` | 宁可拒绝也不能误覆盖 |
| 插件名或目录名**命中名单** | **拒绝**（更新/覆盖安装） | 原有语义 |
| 命中名单 + 卸载且 `force=False` | **拒绝** | 新增闸门（§4） |
| 命中名单 + 卸载且 `force=True` | 放行 | 维护者逃生口（§4） |

## 3. 为什么"缺失"不改成 fail-closed

`maintenance_registry.json` 位于 `<data>/optimization_tracking/`，是**本 fork 的私有机制**。
本项目面向社区开源，**绝大多数用户根本没有这个文件**；
若缺失即拒绝，等于把纯净环境的插件更新/卸载**全部锁死** —— 与
「原版插件 100% 兼容 > fork 效率优化透传」直接冲突。

⇒ 缺失时保持放行，但把**静默**改成**显式告警**，让"保护未启用"这件事可被观测、可被日志检索。

## 4. 卸载闸门与 `force`

- `uninstall_plugin(plugin_name, delete_config=False, delete_data=False, force=False)`
- `uninstall_failed_plugin(dir_name, delete_config=False, delete_data=False, force=False)`
- `force` **默认 False**（保持旧行为：受保护插件不可卸载）；命中名单时报错文案与更新一致，
  提示改用维护仓库的 `update_local.py` 合并/回放。
- **`force` 暂不在 WebUI 暴露**：面板一键误删本地维护版的代价太高，
  需要时在维护脚本里显式传参调用。

## 5. 关于函数名

`assert_plugin_update_allowed` 名字里虽有 "update"，但它保护的是
「**本地维护版被上游或用户丢弃**」这一类变更，现在同时用于更新、覆盖安装与卸载。
**保留原名**（避免 core 内部重命名带来的 shim 成本），docstring 已说明它覆盖三类入口。

## 6. 测试载体

`tests/maintained/test_maintenance_gate.py`：

- 缺失 → 放行且**有 warning 日志**；
- 命中插件名 / 命中目录名 → 拒绝；
- 三种损坏形态（非法 JSON、非 list、含非字符串元素）→ **fail-closed**；
- 卸载：`force=False` 拒绝、`force=True` 绕过闸门（用哨兵异常证明"走到了后续步骤"）。
