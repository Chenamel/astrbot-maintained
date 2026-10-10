# Changelog — AstrBot Maintained Fork

本文件记录**本 fork 相对上游**的变更。上游自身的变更记录见 `changelogs/`（未改动）。

格式参照 Keep a Changelog，版本标签形如 `maintained/v4.28.2-rN`。

## 基线

- **阶段 1 基线**：`3c7adafa1397e182d60b1016bf88759265113c8a`（上游 tag `v4.28.2`）。
- 本 fork 从此提交起家，主干分支 `maintained/v4.28.2`，锚点标签 `baseline/v4.28.2`。

## [未发布]

### 新增

- **阶段 8 存量治理与重构（进行中）**：
  - **P11 定型（T8-01）**：维护版 core 相对上游的 **17 项有意偏离**改为 `xfail(strict=True)` ——
    α 9 项（执行工具授权收紧）、β 8 项（hook 完成时序 = 核心架构优化，保留现状）。
    落地靠**新增文件**：仓库根 `conftest.py` + `maintained/p11_deviations.py` 注册表，
    **上游测试文件一字未改**（零冲突原则）；`strict=True` 让"意外通过"判红，
    即「偏离被回退 / 被上游合并覆盖」的机械报警。
    新护栏 `tests/maintained/test_p11_deviations.py` 守护注册表本身（分组数、nodeid 仍存在、
    理由含组别、β 红线文档仍在、core 锚点仍在、命中数 17/17）。
  - **β 影响面排查（T8-01R）**：新文档 `docs/maintained/hook-timing-impact.md` —— 精确更正 β 根因为
    runner **1130** 行（基线 972 在 yield 之后）；本机 17 个插件**硬风险 0**、受益 2、需观察 1；
    官方生态抽样 71 个仓库（受益 7 / 有风险 3 + 2 待复核），推测真正受损 ≤20–40；
    规划 `hook_timing_mode`（默认 `enhanced` / 可选 `legacy`）的配置、传参与 api 暴露接入点。
    **本轮只出报告，未改 core、未动台账。**
  - 套件口径：`tests/maintained` **186 项**全绿（新增 38 项）；上游口径
    `170 passed, 17 xfailed`、γ 对照 `tests/test_process_stage_images.py` 125 全绿。
    **本阶段不改 core ⇒ 台账 31 条不动、无需重新部署。**
- **阶段 7 安全打磨 + 可用性验证**（发布暂缓，仓库保持私有）：
  - **回归护栏**：`tests/maintained/test_manifest_guard.py`（仓工作树↔台账自洽、台账只含 core、
    `proactive_must_remain_disabled`、条数钉）与 `test_api_frozen.py`（上游 `astrbot/api` 相对
    `baseline/v4.28.2` 零改动，白名单=9 个新增文件）。
  - **core 零行为打磨**：P4 `IMAGE_CAPTION_MARKER` 下沉 core（4 处改引，`astrbot.api.media` 改为
    resolve + 同值兜底）；P5 `_proactive_delivery_deferred` 提升为 `__init__` 正式字段；
    P7 三文件 8 处「被取代回合」门禁补 `logger.debug`；P8 提取 9 个具名常量（值逐字节不变）。
  - **插件**（私有仓）：删死导入 `is_image_part` 与只写不读的 `MAINTAINED_API_AVAILABLE`；
    新增只读自检命令 `enhance api-status`（契约见 `api-contract.md` §7）。
  - **审计发现 P11**：维护版 core 相对纯基线打破上游 **17 项测试预期**（详见 `inventory.md` §4），
    故本阶段 core 打磨的验收标准为「不新增失败」而非「上游测试全绿」。
  - `tests/maintained/` 最终 **94 项**全绿。
- **阶段 6 维护工具链**：`maintained/tools/{check_drift,apply_patches}.py` —— 漂移检测与一键重打。
  只处理台账内文件、默认预演、写前自动备份；用法与边界见
  [`docs/maintained/tools.md`](./docs/maintained/tools.md)。24 项工具测试。
- **阶段 5 插件正规化（api 层部分）**：新增 `astrbot/api/{content,runtime,embedding}/`
  三个模块（纯新增，未改既有 api 文件），把插件剩余的 core 依赖全部纳入公开面。
  契约见 [`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md) §3.0。
  台账 28 → 31 条；`tests/maintained/` 47 → 62 项全绿（阶段 7 后为 94）。
  插件侧改造记录见 [`docs/maintained/deploy-log.md`](./docs/maintained/deploy-log.md)。
- **阶段 3 API 层**：`astrbot/api/` 下新增六个文件（**未修改任何既有 api 文件**）：
  - `_bridge.py` — 内部能力桥（惰性解析 core 符号 + 能力清单，**非公开面**）
  - `media/` — 图片输入契约（**修复 P1**：插件不再需要 import core 私有路径；同时集中 `IMAGE_CAPTION_MARKER`）
  - `turns/` — 直报回合状态读取与 `reset` / `reset_all`
  - `delivery/` — 交付策略纯函数
  - `permissions/` — 权限与执行授权（补丁缺席时**回退管理员判定，不降级为放行**）
  - `proactive/` — 轻量主动判定（开关恒关，模块内不存在 enable 入口）
  - 契约见 `docs/maintained/api-contract.md`；测试 `tests/maintained/`（阶段 3 交付 47 项，后续扩至 94）
- **阶段 2 存量治理产出**：
  - `docs/maintained/inventory.md` — 26 文件逐条分级表（✅必须留 core 17 / 🟡重写保留 4 / ⚪可上移 api 2 / 🔵非 core 前端 4）+ 跨文件共性问题 P1–P10 + 对交接包 5 处事实修正。
  - `docs/maintained/knowledge/` — 存量补丁知识库（11 篇）：三条业务线的业务/技术全景 + 两组成对专题流程（消息合并与取代、图片不可用降级）。
- 仓库骨架：remote（`upstream` 只读 / `origin` 指向本 fork）、主干分支与锚点标签。
- 规范文档 `docs/maintained/`：`proposal.md`、`design.md`、`tasks.md`、`project_rules.md`。
  按 sdd 规范跳过 `docs/layouts/`（本项目无 UI）。
- 合规文件 `NOTICE`（AGPL §13）与 `README_MAINTAINED.md`。
- `.gitattributes`（LF 归一化）与 `.gitignore` 追加段（私有代码黑名单）。
- `maintained/`：`installed_manifest.json`（**仅 core 的 SHA-256 台账，22 条**；该数为脱敏时点值，
  阶段 5 追加 3 个 api 模块后为 **31 条**）、`VERSION`。

### 变更

- **阶段 4 止血（实例侧）**：恢复 26 个 core 补丁 + 部署 6 个 `astrbot/api` 文件到运行实例；
  台账 28/28 SHA-256 一致，`capabilities()` 五项全 `True`，插件 `ImportError` 根因消除。
  机器人启动后已核验**插件加载成功**（插件自身 WebUI 监听 `127.0.0.1:6196`）。
  另将 `active_reply.enable` 由 `true` 改为 `false`（防调试期误发，符合铁律 6）。
  备份位于 `<INST>/optimization_backups/20261009_124413_CST_premaintenance/` 与
  `..._142013_CST_proactive_off/`。详见 [`docs/maintained/deploy-log.md`](./docs/maintained/deploy-log.md)。
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
