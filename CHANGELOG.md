# Changelog — AstrBot Maintained Fork

本文件记录**本 fork 相对上游**的变更。上游自身的变更记录见 `changelogs/`（未改动）。

格式参照 Keep a Changelog，版本标签形如 `maintained/v4.28.2-rN`。

> 本文件是逐阶段施工台账：文中提到的部分 `docs/maintained/...` 文档属维护者内部记录，
> 不随公开仓库分发。当前可查阅的对外文档以 `docs/maintained/` 目录实际内容为准。

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
  - **`hook_timing_mode` 开关落地（T8-07）**：配置项 `agent_runner.config.misc.hook_timing_mode`
    （默认 `enhanced` / 可选 `legacy`），沿 `tool_schema_mode` 的既有链路传到 runner；
    **legacy 只在「上游有对照的路径」延后钩子——即 `tool_loop_agent_runner.py` 的 1130 一处**
    （基线 972 在 yield 之后）；fork 独有的 977（图片降级兜底）与 1325（末轮补生成）保留优化，
    1093 与基线 913 逐字相同故一行不动 ⇒ **legacy 精确等于上游**。
    新增测试 `tests/maintained/test_hook_timing_mode.py` 双模式断言（legacy 下 yield 时钩子未触发＝上游语义）。
  - **cron 与后台任务唤醒路径透传运行时模式（T8-11）**：`cron/manager.py` 的
    `_woke_main_agent` 与 `astr_agent_tool_exec.py` 的
    `_wake_main_agent_for_background_result` **自行构造 `MainAgentBuildConfig`、
    不走 pipeline 的 `agent_sub_stages/internal.py`**，此前不读 misc，于是
    `hook_timing_mode`（连 `tool_schema_mode` 一起）在**定时任务与后台任务场景恒为
    默认值** —— 即使用户配了 `legacy`，这两类唤醒也收不到，逃生舱只覆盖聊天会话。
    现两处一并读 `agent_runner.config.misc`，经 `normalize_hook_timing_mode` 归一化
    （非法值回落 `enhanced`）；**默认配置下行为零变化**（`enhanced` + `full` 恰是原
    数据类默认值）。设计记录见 `docs/maintained/hook-timing-impact.md` §4.6；
    台账 **33 → 35 条**（两文件新登记，守住「改过的 core 必登记」铁规则）；
    新增 `tests/maintained/test_hook_timing_passthrough.py`（12 项，已反向验证：
    把读取改回默认值 → legacy 两项判红）。
  - **P10 手写正则行为台账与钉死测试（T8-02）**：新文档
    `docs/maintained/code-delivery-policy.md` —— 用**实证探针**（而非读正则想象）给出
    `execution_denial` / `SAFETY_REFUSAL_PATTERN` / `code_task_spec` /
    `has_code_delivery` 四张判定矩阵，并**显式登记误判容限**：
    ① 误放行（提权，T8-10）；② 拒答漏判（`病毒`/`木马` 不在风险词表、英文缺风险词、
    拒答措辞后未接指定动词）；③ 拒答误报（含风险词的纯技术说明被判拒答）；
    ④ **新观察**：指定语言时**无标签代码块判不出交付**（围栏正则 `\s*` 吃掉换行，
    首行被当语言标签 ⇒ `not label` 兜底实际走不到）。
    新增 `tests/maintained/test_code_delivery_policy.py`（43 项）钉住**当前实测值**：
    非管理员恒拒等安全不变量用普通断言；已知误判项在 docstring 标注「当前行为 / T8-10 待修」，
    **修复 T8-10 时这些断言会变红 —— 那是要同步更新文档与测试的预期信号**。
    **本轮只钉行为，未改任何实现**（T8-10 严格保持不动）。
  - **P2 core 反向依赖插件目录名 → 能力契约解析（T8-03）**：实测 **2 处**
    （`astr_main_agent._is_lightweight_proactive_request`、`tool_loop_agent_runner._finish_proactive_request`；
    早期清单写的「×2 + ×1」有误，已订正）。两处的真实契约其实是**方法名**（鸭子类型），
    目录名只是「怎么找到它」⇒ 改为在 `star_registry` 里找**已激活且暴露该能力方法**的插件：
    `is_trusted_lightweight_proactive(event)` / `finish_proactive_request(event)`。
    **core 内零插件目录名**、行为逐点等价、**无需改插件**（显式注册表要求插件侧改造并重新部署，
    改造完成前功能会先失效，故本轮采用契约法）。发现规则与理由见
    `docs/maintained/plugin-capability-lookup.md`。
    新增 `tests/maintained/test_plugin_capability_lookup.py`（18 项）：能力发现、
    找不到/未激活/抛异常一律 **fail-closed**、只认字面 `True`、收尾只跑一次；
    **零插件名守卫**（扫 `astrbot/core/**`，命中即红，白名单为空；已反向验证会判红）。
  - **P3 工具名硬编码白名单 → 能力自声明（T8-04）**：两张名单分两半处置 ——
    **A 执行类**（`EXECUTION_TOOL_NAMES`，4 个，**全是 core 自带**）→ **纯自声明**：
    新增 `FunctionTool.is_execution_tool`（照 `is_background_task` 先例，默认关闭），
    4 个工具自己声明，core 改读字段，**不再有任何工具名**；第三方执行工具本来也不在名单里，无回归。
    **B 轻量主动类**（29 个，**绝大多数是第三方插件工具**）→ **自声明 + 配置名单并集**：
    新增 `FunctionTool.is_lightweight_proactive_safe`，并新增配置
    `agent_runner.config.misc.lightweight_proactive_tools`（默认 = 原 29 个，用户可增删）；
    **纯自声明会让主动回复静默失去这批工具**（插件不会来声明），故配置名单必须兜底。
    判定一律 `getattr(tool, <field>, False)` 兜底＝未声明。
    详见 `docs/maintained/tool-capability-declaration.md`。新增
    `tests/maintained/test_tool_capability_declaration.py`（11 项，含「名字不在任何名单里的
    自声明工具也要被移除」这一反回归断言 + 「旧常量不许复活」守卫）。
    **默认配置下行为零变化**（core 自带已声明 + 默认名单 = 原 29 个）。
  - **P9 本地维护保护闸门（T8-06）**：
    ① 名单文件**缺失**原本**静默**放行 ⇒ 改为**明确 `logger.warning`（含路径与原因）后放行**。
    **不改 fail-closed**：`maintenance_registry.json` 是本 fork 私有机制，公开后绝大多数用户
    根本没有它，fail-closed 会把纯净环境的插件更新/卸载**全部锁死**，与兼容立场冲突。
    ② 名单**损坏**（非法 JSON / 结构不对 / 缺键）仍 **fail-closed**（原有语义保留）。
    ③ `uninstall_plugin` / `uninstall_failed_plugin` **补闸门**（此前完全没有），
    并按用户要求留 `force=False` 逃生口；**`force` 暂不在面板暴露**，避免一键误删本地维护版。
    新增 `tests/maintained/test_maintenance_gate.py`（13 项）：缺失必告警、命中插件名/目录名拒绝、
    五种损坏形态 fail-closed、卸载默认被拦 / `force=True` 绕过闸门（用 spy 断言只查一次）。
    详见 `docs/maintained/maintenance-gate.md`。
  - **P6 权限单一入口（T8-05）**：两套权限判定（身份 / 当前消息意图）合到单一入口
    `check_tool_permission(context, operation_name, level)`，级别取 `ToolPermissionLevel.IDENTITY` / `EXECUTION`，
    **无默认级别**（防"忘传就用默认"造成强度漂移）。**判定强度逐点保持现状、行为零变化**（负责人拍板的 A 语义）；
    明确**不合并成 AND** —— 那会把 `execution_denial` 的已知误判（见 T8-10）扩散到原本不看意图的 11 个调点，
    与「原版插件 100% 兼容 > fork 优化」冲突。fork 私有的 `check_execution_permission` **删除**，
    `python.py` / `shell.py` 改调用入口的 `EXECUTION` 级。
    上游符号 `check_admin_permission` 保留为身份级**转发器**（自身无判定逻辑）：它在
    `computer_tools.__all__` 导出，且上游测试 `tests/unit/test_cua_computer_use.py` **以该名做 monkeypatch**
    ⇒ `cua.py` / `fs.py` / `message_tools.py` / `shipyard_neo/*` 这 5 个干净的上游文件**一行未动**
    （改了既违反零冲突原则，又要让台账从 36 涨到 41 去登记本不需要的改动）。
    详见 `docs/maintained/tool-permission-entry.md`。新增
    `tests/maintained/test_tool_permission_entry.py`（16 项）：两个级别各自的行为、**级别互不叠加**、
    `check_admin_permission` 无自有逻辑、旧并行入口已消失、15 个调点的级别映射不漂移。
  - **长期记忆入库与内容安全审计的先后（T8-09，观察项）**：**结论 = 不存在"入库早于审计"**，
    **本轮只落文档、未写 core 代码、未动台账**。证据链：`star_handler` 按 `priority` **降序**执行（缺省 0），
    审计钩子 `priority=1000` 先于记忆钩子；审计失败时**原地改写同一个 `LLMResponse`**；
    拦截会 `stop_event()`，事件钩子循环在每个 handler 之后检查 ⇒ 后续钩子（含记忆反射）不再执行；
    审计重试走 `context.llm_generate()`（直连 provider、**不派发事件钩子**）⇒ 中间被拒文本不会二次入库。
    真正的脆弱点改写为**覆盖盲区**：审计插件 `group_only=True` ⇒ **私聊零审计**；输入检查关闭 ⇒ **用户发言零审计**
    （记忆插件用自定义过滤器**被动捕获**群消息，不唤醒 AstrBot）；群聊输出侧实际只剩「LLM 审查 + 1 次重试」。
    三项均属**插件配置/插件侧**范畴，core 不动。附带发现（**仅记录不修**）：记忆钩子缺 `is_chunk` 判断，
    当前因该事件只在 `on_agent_done` 派发且传最终聚合响应而不触发。
    详见 `docs/maintained/livingmemory-audit-order.md`。
  - **β 影响面排查（T8-01R）**：新文档 `docs/maintained/hook-timing-impact.md` —— 精确更正 β 根因为
    runner **1130** 行（基线 972 在 yield 之后）；本机 17 个插件**硬风险 0**、受益 2、需观察 1；
    官方生态抽样 71 个仓库（受益 7 / 有风险 3 + 2 待复核），推测真正受损 ≤20–40；
    规划 `hook_timing_mode`（默认 `enhanced` / 可选 `legacy`）的配置、传参与 api 暴露接入点。
    **legacy 范围定稿为「只延后 1130 / 1325」**：1093 与基线 913 逐字相同故保持不动（动它只会偏离上游），
    977 经实测为独立的图片降级早退路径故保持 `enhanced` —— **legacy 精确等于上游行为**。
    另登记 **T8-10**：`execution_denial` 误放行（引用文档即授权执行，**提权风险**），单独排期，本阶段不改。
    **本轮只出报告，未改 core、未动台账。**
  - 套件口径（截至 T8-05 / T8-09）：`tests/maintained` **304 项**（303 passed + 1 skipped，22 个文件）；
    上游口径 `295 passed, 17 xfailed`（含 γ 对照 `tests/test_process_stage_images.py` 125）；
    台账 **36 条**（T8-07 +4、T8-11 +2、T8-04 +1；**T8-05 无新增登记，只同步 3 条哈希**），双端 NO DRIFT。
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
  插件侧改造记录见 `docs/maintained/deploy-log.md`（维护者内部记录）。
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
  `..._142013_CST_proactive_off/`。详见 `docs/maintained/deploy-log.md`（维护者内部记录）。
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
