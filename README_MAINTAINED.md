# AstrBot Maintained Fork

一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的**维护型源码 fork**，锁基线于 `v4.28.2`。

本文件是**维护者向**的说明（基线、台账、上游同步）；面向访客的主页说明见
[`README.md`](./README.md)（本 fork 自写版，已替换上游默认 README）。

## 这是什么

- 上游：`AstrBotDevs/AstrBot`（AGPL-3.0，无附加例外）
- 基线：tag `v4.28.2` → commit `3c7adafa1397e182d60b1016bf88759265113c8a`
- 主干分支：`maintained/v4.28.2`（长期维护线，升基线不改名）
- 锚点标签：`baseline/v4.28.2`（永久指向基线提交，供回滚与三方合并比对）

## 设计立场

1. **兼容优先**：`astrbot.api.*` 与插件事实依赖的 core 路径全部冻结，原版插件零改动可用。
2. **只做加法**：新增能力一律落 `astrbot/api/**`，core 内部保持最小侵入，新开关默认保持旧行为。
3. **可回归**：core 改动登记 `maintained/installed_manifest.json`（SHA-256 台账），可一键校验。
4. **合规**：AGPL §13 义务见 [`NOTICE`](./NOTICE)；变更台账见 [`CHANGELOG.md`](./CHANGELOG.md)。

## 目录约定（零冲突原则）

本 fork 自有内容一律走新增路径，不修改上游既有文件：

| 路径 | 用途 |
|---|---|
| `maintained/` | 版本、SHA-256 台账、维护工具 |
| `docs/maintained/` | 规范文档（proposal / design / tasks / project_rules） |
| `tests/maintained/` | 本 fork 的测试 |
| `CHANGELOG.md` | 相对上游的变更台账（区别于上游 `changelogs/`） |

## 上游同步

```bash
git fetch upstream --tags --prune
git switch -c tmp/sync-<ref> maintained/v4.28.2
git merge --no-commit --no-ff <upstream ref>
# 校验台账与实例一致性：见 maintained/README.md 的比对脚本
```

## 许可证

AGPL-3.0-or-later，与上游一致。完整文本见 [`LICENSE`](./LICENSE)（未改动）。
本 fork 与 AstrBot 作者无从属或背书关系。
