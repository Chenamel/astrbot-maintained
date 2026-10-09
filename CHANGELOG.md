# Changelog — AstrBot Maintained Fork

本文件记录**本 fork 相对上游**的变更。上游自身的变更记录见 `changelogs/`（未改动）。

格式参照 Keep a Changelog，版本标签形如 `maintained/v4.28.2-rN`。

## 基线

- **阶段 1 基线**：`3c7adafa1397e182d60b1016bf88759265113c8a`（上游 tag `v4.28.2`）。
- 本 fork 从此提交起家，主干分支 `maintained/v4.28.2`，锚点标签 `baseline/v4.28.2`。

## [未发布]

### 新增

- **阶段 3 API 层**：`astrbot/api/` 下新增六个文件（**未修改任何既有 api 文件**）：
  - `_bridge.py` — 内部能力桥（惰性解析 core 符号 + 能力清单，**非公开面**）
  - `media/` — 图片输入契约（**修复 P1**：插件不再需要 import core 私有路径；同时集中 `IMAGE_CAPTION_MARKER`）
  - `turns/` — 直报回合状态读取与 `reset` / `reset_all`
  - `delivery/` — 交付策略纯函数
  - `permissions/` — 权限与执行授权（补丁缺席时**回退管理员判定，不降级为放行**）
  - `proactive/` — 轻量主动判定（开关恒关，模块内不存在 enable 入口）
  - 契约见 `docs/maintained/api-contract.md`；测试 `tests/maintained/`（47 项）
- **阶段 2 存量治理产出**：
  - `docs/maintained/inventory.md` — 26 文件逐条分级表（✅必须留 core 17 / 🟡重写保留 4 / ⚪可上移 api 2 / 🔵非 core 前端 4）+ 跨文件共性问题 P1–P10 + 对交接包 5 处事实修正。
  - `docs/maintained/knowledge/` — 存量补丁知识库（11 篇）：三条业务线的业务/技术全景 + 两组成对专题流程（消息合并与取代、图片不可用降级）。
- 仓库骨架：remote（`upstream` 只读 / `origin` 指向本 fork）、主干分支与锚点标签。
- 规范文档 `docs/maintained/`：`proposal.md`、`design.md`、`tasks.md`、`project_rules.md`。
  按 sdd 规范跳过 `docs/layouts/`（本项目无 UI）。
- 合规文件 `NOTICE`（AGPL §13）与 `README_MAINTAINED.md`。
- `.gitattributes`（LF 归一化）与 `.gitignore` 追加段（私有代码黑名单）。
- `maintained/`：`installed_manifest.json`（**仅 core 的 SHA-256 台账，22 条**）、`VERSION`。

### 变更

- `README.md` 替换为本 fork 说明（GitHub 首页渲染入口）。这是**唯一**被修改的上游既有文件：
  `.gitattributes` 声明 `README.md merge=ours` 并配置对应 merge driver，
  上游对 README 的改动永不覆盖本 fork 版本；其余全部上游文件（含 `docs/`、
  `AGENTS.md`、多语言 README 等，合计约 2.4MB 的 md）**保持原样不删**——
  它们已永久存在于 git 历史，删除不节省空间，只会制造三方合并冲突。
- 台账脱敏：剔除 `data/plugins/**`（39 条）与 `dashboard/**`（4 条），只保留 `astrbot/**`（22 条）。
  理由：本仓是 core 项目，第三方插件无许可证、其文件清单不宜公开；完整台账留在归档仓与私有仓。
- 移除 `maintained/tools/update_local.py`：该脚本含 enhance/safety 分支与插件名，
  属实例运维工具而非 core 本体；保留在归档仓与私有仓，阶段 6 按类官方范式重写工具链。

### 定位

- 既有增强插件**仅作参考实现**（后续大概率重写）；本 fork 优先完善 core 与 `astrbot/api/**`。

### 未做

- 未修改任何 core 代码；未恢复任何补丁（止血在阶段 4）。
- 未引入第三方插件源码（该插件无许可证，只能进私有仓）。
