# Proposal — AstrBot Maintained Fork

> 本文件回答「做什么」。不写具体代码实现。
> layouts 说明：本项目为纯后端核心与插件 API，无 UI 界面，按 sdd 规范**跳过 `docs/layouts/`**；将来若新增管理面板再补。

## 1. 背景与问题

1. AstrBot 运行实例的 core 曾被打过 **26 个补丁（+1639 / -91 行）**；2026-10-08 启动器更新核心后，补丁被官方 core 覆盖丢失。
2. 增强插件因顶层语句 `from astrbot.core.provider.entities import IMAGE_INPUT_UNAVAILABLE_NOTICE` 导入失败，导致整个 4316 行的 `main.py` **无法加载**（一处顶层 import 失败即全插件失效）。
3. **根因不是补丁错，是架构错**：插件硬依赖 core 私有路径且无降级兜底 → core 一动，插件全死。
4. 现有维护仓 `maintenance_repos/astrbot_local` 是**快照式归档**（6 commit、无 remote、其中 `upstream/core` 为 depth=1 浅克隆），无法做三方合并、无法对外发布、无法复现基线。
5. 需要的是一个**能长期演进、能回溯、能合规公开**的 fork 仓库，把补丁升格为「有稳定公开 API 的维护分支」。

## 2. 目标（可度量）

| ID | 目标 | 度量方式 |
|---|---|---|
| G1 | 基线可复现 | 任意机器 clone 后 `git rev-parse baseline/v4.28.2` 可达 `3c7adafa`，且工作区字节与上游一致（CRLF 计数为 0） |
| G2 | 对外兼容 | 原版插件**零改动**可用；`astrbot.api.*` 与事实公开符号全部冻结 |
| G3 | 只做加法 | 新增能力一律落 `astrbot/api/**`，不触碰既有对外可见路径 |
| G4 | 合规 | 满足 AGPL §13：公开仓库 + `NOTICE` + 同源可获取 |
| G5 | 可回归 | 每个 core 改动登记 SHA-256 台账，阶段 4 起每个改动附测试 |

## 3. 明确不做的事情

- 不做 UI / 前端（不重写 `dashboard/`）。
- **不把第三方增强插件源码放入公开仓**（该插件无任何许可证），只能进私有仓 `astrbot-extras`。
- **不重命名、不删除** `astrbot.api.*` 现存符号，以及 core 中被插件事实依赖的 5 个路径。
- 不做上游版本升级：**锁 v4.28.2**（`v4.29.0-beta.1` 暂不跟），升级走三方合并并单独立项。
- **不开主动回复开关**（`proactive_must_remain_disabled` 恒为 true）。
- 不新增运行时依赖、不引入新 CI 平台。
- 不批量格式化既有代码（不 `git add --renormalize .`、不全局 reformat）。
- 不动 `data/` 运行时数据、不动 venv、不动密钥配置。
- 不修改上游既有文件（`LICENSE` / `EULA.md` / `pyproject.toml` / `astrbot/__init__.py` / `README*.md` / `changelogs/`）。

## 4. 用户与受影响方

- **实例运维者**：需要机器人可恢复、补丁可重放、升级不失控。
- **插件作者**（第三方与自研）：需要稳定 import 面，不因 core 变动而整体崩溃。
- **上游 AstrBotDevs**：fork 需明确标注来源与许可，不冒用其名义。

## 5. 术语与基线事实表

| 术语 | 含义 |
|---|---|
| upstream | `AstrBotDevs/AstrBot`，AGPL-3.0，默认分支 `master` |
| baseline | tag `v4.28.2` → commit `3c7adafa1397e182d60b1016bf88759265113c8a` |
| maintained | 本 fork 主干分支 `maintained/v4.28.2`；锚点 tag `baseline/v4.28.2` |
| api 层 | `astrbot/api/**`，对插件公开的唯一稳定面 |
| core 内部 | `astrbot/core/**`，除已登记补丁外不得作为插件依赖面 |
| extras | 私有仓 `Chenamel/astrbot-extras`（永远私有，无许可证） |

**4.28.2 真实布局**：`astrbot/core/...`（非旧的 `astrbot/...`）。

## 6. 方案概述（七阶段）

```
1 建仓骨架 → 2 存量治理 → 3 API 层 → 4 修机器 → 5 插件正规化 → 6 工具 → 7 发布
```

先治理后止血：机器人在此期间的故障态被接受，止血集中在阶段 4。

## 7. 范围边界

只覆盖 **core fork 与插件兼容层**。不含：部署运维、模型选型、dashboard 前端、上游功能开发。

既有增强插件**只作为参考实现**（其"主动回复"等能力后续大概率重写）；本 fork 的代码范式以**类官方风格**为准，不迁就旧插件的写法。

## 8. 验收标准（每条可命令验证）

- **A1** `git rev-parse baseline/v4.28.2` = `3c7adafa…`（锚点标签永久指向基线，主干 HEAD 随维护推进而前进），`git status --porcelain` 为空，本地无 `master` 分支。
- **A2** `git remote -v`：`upstream` 禁推、`origin` 为 SSH `Chenamel/astrbot-maintained`；`ssh -T git@github.com` 返回 Chenamel。
- **A3** `astrbot/__init__.py` 与 `pyproject.toml` 版本均为 `4.28.2`。
- **A4** 全仓 grep 无增强插件名、无 `Axi404`、`git ls-files` 无 `data/plugins` 路径。
  ⚠️ **当前未达成（暂缓）**：仍有 2 处 core 站点（P2：`astr_main_agent.py`、`tool_loop_agent_runner.py` 的插件目录名匹配）
  + `.gitignore` 黑名单 + 3 篇内部文档。发布转公开前必须一并处理；守卫测试的实现在 P2 完成后才有意义。
- **A5** `ruff check .` 相对基线**零新增**错误。
- **A6** 四份 sdd 文档齐备（layouts 已声明跳过）。

## 9. 风险与假设

沿用风险登记 R1–R6：存量代码无测试、插件无许可证、启动器持续覆盖、四处状态脱节、主动回复误开、上游语义不兼容。

## 10. 依赖与前置

SSH 密钥 `id_ed25519_workbuddy`、GitHub 账号 `Chenamel`、Python 3.12 venv、`ruff==0.15.22`、归档仓 `maintenance_repos/astrbot_local`（只读）。

## 11. 决策记录

| ID | 决策 |
|---|---|
| D1 | 锁 v4.28.2 为基线，不跟 v4.29.0-beta.1 |
| D2 | 双仓：公开 `astrbot-maintained`（AGPL-3.0）+ 私有 `astrbot-extras`（无许可证） |
| D3 | 先治理后止血（1→2→3→4→5→6→7） |
| D4 | 兼容优先、最大化增强：对外冻结 + 内部加法 |
| D5 | 建仓即私有，阶段 7 转公开 |
| D6 | 不引入 open-source-license-check（许可证结论已核实，避免工具堆叠） |
| D7 | 增强插件**仅作参考实现**，后续大概率重写；本 fork **优先完善 core 与 `astrbot/api/**`**，按类官方范式写代码 |
