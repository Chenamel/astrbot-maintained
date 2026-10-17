# AstrBot 维护版（Maintained Fork）

> 官方 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的长期维护分支，基线锁定 `v4.28.2`。
> 一句话：**官方插件不用改一行就能用**，在此之上补一些官方没有的底层能力。
>
> A maintained fork of AstrBot pinned to the `v4.28.2` baseline: drop-in compatible
> with upstream plugins, plus a few extra low-level APIs.

---

## 它是什么

一个**独立仓库**（不在 GitHub 的 fork 网络里，也从不往上游推东西）。我们做的是：

- 拿上游 `v4.28.2` 的代码当基线
- 修问题、补能力、做安全加固
- 但**保证官方插件拿来就能跑**

上游发布新版本时，我们会挑着合并过来；基线本身不轻易升。

## 和官方版有什么不一样

能实际感觉到的差别就这几条，而且**默认都跟官方一致**：

| 能力 | 默认（跟官方一样） | 可选（本 fork 才有） |
|---|---|---|
| Python / Shell 执行授权 | 只校验管理员权限 | `严格`模式：还要求你在**这条消息里**明确说“运行/执行”，引用文档里的“先编译，再运行”不再算授权 |
| 完成钩子时序 | `原版`：回复先发出、钩子后触发 | `增强`：钩子先触发，审计/改写类插件能抢在回复发出前介入 |
| 插件可用的扩展 API | — | `astrbot/api/**`：回合状态、交付策略、权限、媒体、运行时等（官方没有） |
| 主动回复 | **默认关闭**（防止机器人自作主张刷屏） | 可自行开启 |

想切换这些开关：进面板 → 配置页，每一项都有中文说明。

## 想装来用？

用法和官方 AstrBot 完全一样（launcher 或源码启动都行），配置文件也兼容。

⚠️ **一条提醒**：面板顶部如果出现“AstrBot 有新版本”，**不要点升级**——那是上游 v4.29+，会把本 fork 的改动冲掉。想跟进新版本请等我们合并，或者自己合（见维护者文档）。

## 给插件开发者

- 新增能力全部落在 `astrbot/api/**`，外部只 `import astrbot.api.*`
- `astrbot.api.*` 和插件实际依赖的 core 路径**冻结**，不会突然改掉
- 想用新增能力（查询回合状态、判断执行权限等），翻 `astrbot/api/` 下的模块即可

## 常见问题

**官方插件能直接用吗？**
能。兼容是本 fork 的第一优先级；一旦和我们的优化冲突，无条件退让给官方行为。

**能升到官方最新版吗？**
不建议直接升。我们按自己的节奏合并上游；你会 git 的话也可以自己合。

**发现 bug / 想提需求？**
直接开 issue，附上日志会很有帮助（日志默认写在 `data/logs/astrbot.log`）。

**这个仓库会公开吗？**
远期计划公开，但有几处内容需要先脱敏，具体进度见 `docs/maintained/roadmap.md`。

## 文档导航

| 想看什么 | 去哪 |
|---|---|
| 维护者向说明（基线、台账、怎么同步上游） | [`README_MAINTAINED.md`](./README_MAINTAINED.md) |
| 规范与决策记录 | [`docs/maintained/`](./docs/maintained/)（design / project_rules / tasks / roadmap / inventory） |
| 相对上游的改动清单 | [`CHANGELOG.md`](./CHANGELOG.md) |
| core 改动台账（SHA-256，可脚本校验） | [`maintained/installed_manifest.json`](./maintained/installed_manifest.json) |
| 上游官方说明 | [`README_zh.md`](./README_zh.md) 等，或 [上游仓库](https://github.com/AstrBotDevs/AstrBot) |

## 许可证

AGPL-3.0-or-later，与上游一致，完整文本见 [`LICENSE`](./LICENSE)（未改动）。
本 fork 与 AstrBot 作者无从属或背书关系。
