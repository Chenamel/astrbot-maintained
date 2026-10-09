# AstrBot Maintained Fork

一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的**维护型源码 fork**，基线锁定于 `v4.28.2`。

> 上游原 README（简体中文等多语言版本）见 [AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot)，
> 或本仓 `README_zh.md` 等文件；上游原文也可随时从 `upstream/master` 取回。

## 这是什么

- **上游**：`AstrBotDevs/AstrBot`（AGPL-3.0，无附加例外）
- **基线**：tag `v4.28.2` → commit `3c7adafa1397e182d60b1016bf88759265113c8a`
- **主干分支**：`maintained/v4.28.2`（长期维护线，升基线不改名）
- **锚点标签**：`baseline/v4.28.2`（永久指向基线提交，供回滚与三方合并比对）

这是一个**独立仓库**（非 GitHub fork 网络），不向上游推送任何内容；
本仓的定位是「兼容优先的维护版核心 + 插件公开 API 层」。

## 设计立场

1. **兼容优先**：`astrbot.api.*` 与插件事实依赖的 core 路径全部冻结，原版插件零改动可用。
2. **只做加法**：新增能力一律落 `astrbot/api/**`；core 内部最小侵入，新开关默认保持旧行为。
3. **core 优先**：按类官方范式写代码；存量第三方插件仅作参考实现，不迁就其写法。
4. **可回归**：core 改动登记 `maintained/installed_manifest.json`（SHA-256 台账），可脚本化校验。
5. **合规**：AGPL §13 义务见 [`NOTICE`](./NOTICE)；变更台账见 [`CHANGELOG.md`](./CHANGELOG.md)。

## 目录导览

| 路径 | 说明 |
|---|---|
| [`README_MAINTAINED.md`](./README_MAINTAINED.md) | 本 fork 的详细说明（设计立场 / 上游同步 / 台账校验） |
| [`maintained/`](./maintained/) | 版本、core 受保护文件 SHA-256 台账 |
| [`docs/maintained/`](./docs/maintained/) | 规范文档：proposal / design / tasks / project_rules |
| [`tests/maintained/`](./tests/maintained/) | 本 fork 的测试 |
| [`CHANGELOG.md`](./CHANGELOG.md) | 相对上游的变更台账（区别于上游 `changelogs/`） |
| `astrbot/`、`dashboard/`、`docs/` 等 | 上游内容，除已登记补丁外**保持原样** |

## 上游同步

```bash
git fetch upstream --tags --prune
git switch -c tmp/sync-<ref> maintained/v4.28.2
git merge --no-commit --no-ff <upstream ref>
# 骨架文件因零冲突原则不应冲突；README.md 由 merge=ours 策略自动保留本 fork 版本
```

## 许可证

AGPL-3.0-or-later，与上游一致，完整文本见 [`LICENSE`](./LICENSE)（未改动）。
本 fork 与 AstrBot 作者无从属或背书关系。
