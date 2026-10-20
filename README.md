# AstrBot 维护版（Maintained Fork）

> 官方 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的长期维护分支，基线锁定 `v4.28.2`。
> 上游插件无需修改即可运行，并在此基础上补充上游未提供的底层能力。
>
> A maintained fork of AstrBot pinned to the `v4.28.2` baseline: drop-in compatible
> with upstream plugins, plus a few extra low-level APIs.

---

## 项目定位

本仓库为**独立仓库**：不在 GitHub 的 fork 网络中，也不会向上游推送任何提交。我们的工作包括：

- 以上游 `v4.28.2` 为基线
- 修复缺陷、补充能力，并进行安全加固
- 保证上游插件无需修改即可运行

上游发布新版本后按需合并；基线本身不随上游升级而变动。

## 与上游版本的差异

可感知的差异如下，且**默认行为均与上游一致**：

| 能力 | 默认（与上游一致） | 可选（本 fork 提供） |
|---|---|---|
| Python / Shell 执行授权 | 仅校验管理员权限 | `严格` 模式：还需在当前消息中明确要求“运行/执行”；引用文档中的“先编译，再运行”不再视为授权 |
| 完成钩子时序 | `原版`：回复先发出，钩子后触发 | `增强`：钩子先触发，审计与改写类插件可在回复发出前介入 |
| 插件可用的扩展 API | — | `astrbot/api/**`：回合状态、交付策略、权限、媒体、运行时等（上游未提供） |
| 主动回复 | **默认关闭**，避免机器人在未被触发时自行发言 | 可按需开启 |

各项开关可在**面板 → 配置页**中调整，每项均附中文说明。

## 安装与使用

使用方式与官方 AstrBot 一致：支持 launcher 与源码两种启动方式，配置文件亦保持兼容。

⚠️ **注意**：面板顶部若提示“AstrBot 有新版本”，**请勿升级**。该提示指向上游 v4.29+，升级会覆盖本 fork 的改动。如需跟进新版本，请等待本仓库合并，或自行合并（参见维护者文档）。

## 面向插件开发者

- 新增能力全部落在 `astrbot/api/**`，外部仅需 `import astrbot.api.*`
- `astrbot.api.*` 及插件实际依赖的 core 路径均已冻结，不会在次要版本中变更
- 如需使用新增能力（查询回合状态、判断执行权限等），可查阅 `astrbot/api/` 下的对应模块

## 常见问题

**上游插件可以直接使用吗？**
可以。兼容性是本 fork 的第一优先级；当与本 fork 的优化冲突时，一律退让给上游行为。

**能否升级到上游最新版本？**
不建议直接升级。我们按自身节奏合并上游改动；也可自行合并（参见维护者文档）。

**发现缺陷或有功能建议？**
欢迎直接提交 issue，建议附上日志（默认位于 `data/logs/astrbot.log`）。

**本仓库会公开吗？**
远期计划公开，但仍有部分内容需要先完成脱敏，进度见 `docs/maintained/roadmap.md`。

## 文档导航

| 需要了解的内容 | 位置 |
|---|---|
| 维护者向说明（基线、台账、上游同步） | [`README_MAINTAINED.md`](./README_MAINTAINED.md) |
| 规范与决策记录 | [`docs/maintained/`](./docs/maintained/)（design / project_rules / tasks / roadmap / inventory） |
| 相对上游的改动清单 | [`CHANGELOG.md`](./CHANGELOG.md) |
| core 改动台账（SHA-256，可脚本校验） | [`maintained/installed_manifest.json`](./maintained/installed_manifest.json) |
| 上游官方说明 | [`README_zh.md`](./README_zh.md) 等，或 [上游仓库](https://github.com/AstrBotDevs/AstrBot) |

## 许可证

AGPL-3.0-or-later，与上游一致；完整文本见 [`LICENSE`](./LICENSE)（未改动）。
本 fork 与 AstrBot 作者无从属或背书关系。
