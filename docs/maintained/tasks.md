# Tasks — AstrBot Maintained Fork

> `layouts/` 说明：本项目为纯后端核心与插件 API，无 UI 界面，按 sdd 规范**跳过**；将来若新增管理面板再补。

## 编号规则

`T{阶段号}-{两位序号}`

| 前缀 | 阶段 |
|---|---|
| `T0-` | sdd 元任务（含 layouts 跳过声明） |
| `T1-` | 阶段 1 建仓骨架 |
| `T2-` | 阶段 2 存量治理 |
| `T3-` | 阶段 3 API 层 |
| `T4-` | 阶段 4 修机器（止血） |
| `T5-` | 阶段 5 插件正规化 |
| `T6-` | 阶段 6 工具链 |
| `T7-` | 阶段 7 打磨与可用性验证（**发布暂缓，保持私有**） |

表头（10 列，顺序固定）：
`编号 | 优先级 | 前置依赖 | 涉及文件 | 工作内容 | 完成标准 | 验证方式 | 可否并行 | 状态 | 提交信息`

优先级：P0 阻断 / P1 高 / P2 中 / P3 低。

## 阶段 1 · 建仓骨架

| 编号 | 优先级 | 前置依赖 | 涉及文件 | 工作内容 | 完成标准 | 验证方式 | 可否并行 | 状态 | 提交信息 |
|---|---|---|---|---|---|---|---|---|---|
| T0-00 | P0 | — | docs/maintained/* | layouts 跳过声明（无 UI） | proposal 与 tasks 各有一行声明 | 目视 | — | ✅ | docs(sdd): add proposal for maintained AstrBot fork |
| T1-01 | P0 | — | 全局 git config | 置 `autocrlf=false` / `eol=lf` / `longpaths=true` | `git config --get core.autocrlf` = `false` | 命令回显 | 是 | ✅ | （无提交） |
| T1-02 | P0 | T1-01 | D:/asbot_core_for_fork | 全量 clone 上游（不用 `--depth`/`--filter`） | `git rev-parse 'v4.28.2^{}'` = `3c7adafa` | 命令 | 否 | ✅ | （clone） |
| T1-03 | P0 | T1-02 | .git/config | `origin`→改名 `upstream` 并禁推；新增 `origin`=SSH | `git remote -v` 3 条正确 | 命令 | 否 | ✅ | （无提交） |
| T1-04 | P0 | T1-03 | refs | 切 `maintained/v4.28.2`；打 `baseline/v4.28.2`；删本地 `master` | HEAD=`3c7adafa` 且本地无 master | 命令 | 否 | ✅ | （无提交） |
| T1-05 | P0 | — | GitHub | 建两个私有仓 `astrbot-maintained` / `astrbot-extras`（autoInit=false） | 两仓存在且为空 | GitHub 页面 | 是 | ✅ | （无提交） |
| T1-06 | P0 | T1-04, T1-05 | refs | 显式 refspec 推分支 + 2 个 tag（禁 `--all`/`--mirror`） | `git ls-remote origin` 含 3 ref、无 master | 命令 | 否 | ✅ | （push） |
| T1-07 | P1 | T1-04 | docs/maintained/proposal.md | 写 proposal（含"不做"与验收） | 11 节齐全 | 目视 | 否 | ✅ | docs(sdd): add proposal for maintained AstrBot fork |
| T1-08 | P1 | T1-07 | docs/maintained/design.md | 写 design（含对应关系表与降级方案） | 13 节齐全 | 目视 | 否 | ✅ | docs(sdd): add design and compatibility boundary |
| T1-09 | P1 | T1-08 | docs/maintained/tasks.md | 写任务表 | 编号规则生效 | 目视 | 否 | ✅ | docs(sdd): add phased task table |
| T1-10 | P1 | T1-09 | docs/maintained/project_rules.md | 写执行规则（六铁律） | 六铁律逐条可指认 | 目视 | 否 | ✅ | docs(sdd): add project rules (six invariants) |
| T1-11 | P1 | T1-04 | NOTICE, README_MAINTAINED.md | AGPL §13 声明 + fork 说明 | 含上游 URL / 基线 sha / 许可 | grep | 是 | ✅ | docs: add AGPL section 13 notice and fork README |
| T1-12 | P1 | T1-04 | .gitattributes, .gitignore | LF 归一化 + 私有代码黑名单（仅末尾追加） | 上游原有行未改 | `git diff` | 是 | ✅ | chore: add gitattributes and hardened gitignore |
| T1-13 | P2 | T1-04 | maintained/** | 从归档仓只读复制台账与校验器 | 两端 sha256 一致 | sha256sum 比对 | 是 | ✅ | chore: import maintenance tooling snapshot from archived astrbot_local |
| T1-14 | P2 | T1-04 | CHANGELOG.md | 初始化变更台账 | 含"阶段 1 基线：3c7adafa" | 目视 | 是 | ✅ | docs: initialize maintained changelog |
| T1-15 | P0 | T1-10..14 | 全仓 | 私有代码残留扫描 + 换行/体积体检 | 三条 grep 全空 | 见 project_rules §6 | 否 | ✅ | （无提交） |
| T1-16 | P0 | T1-15 | — | **阶段门禁：停下汇报 ≤10 行，等用户确认** | 已汇报且确认 | 对话记录 | 否 | ✅ | — |

## 后续阶段（粗粒度占位，进入各阶段前细化）

| 编号 | 优先级 | 前置依赖 | 涉及文件 | 工作内容 | 完成标准 | 验证方式 | 可否并行 | 状态 | 提交信息 |
|---|---|---|---|---|---|---|---|---|---|
| T2-01 | P1 | T1-16 | docs/maintained/ | 逆向存量 1639 行（26 文件），产出知识库与分级结论 | 每个补丁有"必须留 core / 重写保留 / 上移 api / 非 core"判定 | 评审 + 链接/敏感/格式校验 | 否 | ✅ | docs(knowledge): reverse-engineer 26 legacy patches, add inventory and knowledge base |
| T2-02 | P1 | T2-01 | docs/maintained/inventory.md | 输出跨文件共性问题 P1–P10 与交接包修正 5 处 | 每条有位置与处置 | 评审 | 否 | ✅ | 同上 |
| T3-00 | P0 | T2-02 | docs/maintained/api-contract.md | 写 API 契约（签名/降级语义/测试要求） | 五模块符号与降级表齐全 | 评审 | 否 | ✅ | docs(sdd): add api contract for phase 3 |
| T3-01 | P0 | T3-00 | astrbot/api/_bridge.py | 内部桥：惰性解析 + 能力清单 | 缺补丁时返回默认值且只记一次日志 | pytest | 否 | ✅ | feat(api): add capability bridge with graceful degradation |
| T3-02 | P0 | T3-01 | astrbot/api/media/ | 图片输入契约（P1 修复：常量不再依赖 core 私有路径） | 常量与 core 值一致；判定函数可用 | pytest | 是 | ✅ | feat(api): expose media input contract |
| T3-03 | P0 | T3-01 | astrbot/api/turns/ | 回合状态访问与 `reset`/`reset_all` | 补丁缺席时 `is_current→True`、`reset*→False` | pytest | 是 | ✅ | feat(api): expose direct turn state access |
| T3-04 | P1 | T3-01 | astrbot/api/delivery/ | 交付策略纯函数对外 | 缺席时返回安全默认值 | pytest | 是 | ✅ | feat(api): expose delivery policy helpers |
| T3-05 | P1 | T3-01 | astrbot/api/permissions/ | 权限与执行授权 | 缺席时**回退管理员判定，不得无条件放行** | pytest | 是 | ✅ | feat(api): expose permission and execution policy |
| T3-06 | P1 | T3-01 | astrbot/api/proactive/ | 轻量主动判定（开关恒关） | `proactive_switch_is_disabled→True` | pytest | 是 | ✅ | feat(api): expose proactive capability flag (always disabled) |
| T3-07 | P0 | T3-02..06 | tests/maintained/test_api_*.py | 六份测试 | 全绿且不依赖运行中的 AstrBot | pytest | 否 | ✅ | test(api): cover additive api surface and degradation |
| T3-08 | P0 | T3-07 | maintained/installed_manifest.json | 新文件登记 SHA-256（铁律 5） | 台账含全部新增 api 文件 | 校验脚本 | 否 | ✅ | chore: register new api modules in manifest |
| T3-09 | P0 | T3-08 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ✅ | — |
| T4-01 | P0 | T3-09 | core 实例 | 备份 → 恢复 26 补丁 + 6 api 文件 → SHA 校验（**后扩至 31 条**） | 台账 28/28（阶段 5 后 31/31）一致、capabilities 全 True | 实测 | 否 | ✅ | （实例侧操作，见 docs/maintained/deploy-log.md） |
| T4-02 | P0 | T4-01 | 实例运行 | 启动 AstrBot，确认插件加载成功 | 日志无 ImportError、机器人可响应 | 实测日志 | 否 | ✅ | 已核验：PID 211524 监听 6199/6185，插件 WebUI 6196 在听 → 插件已加载 |
| T4-03 | P0 | T4-02 | 插件配置 | **铁律 6**：`active_reply.enable` 置 `false`（防调试误发） | 重启后仍为 `false` 且逐项语义比对只差该 1 项 | 目视 + 语义比对 | 否 | ✅ | （实例侧，见 deploy-log.md） |
| T4-04 | P0 | T4-03 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ✅ | — |
| T5-00 | P0 | T4-04 | docs/maintained/api-contract.md | 写阶段 5 接口契约（3 个新模块 + 改造规则） | 契约齐全 | 评审 | 否 | ✅ | docs(sdd): specify phase 5 api additions |
| T5-01 | P0 | T5-00 | D:/asbot_extras | 建私有仓（本地 + GitHub），插件原样入库做基线 | 31 文件逐字节一致、已推送 | sha256 比对 + 远端 refs | 否 | ✅ | chore: import plugin source as maintenance baseline |
| T5-02 | P0 | T5-00 | 插件 8 处 import | `import astrbot.core...` → `astrbot.api.*` + `try/except ImportError` 降级 | 插件内零 `astrbot.core` 引用 | grep | 否 | ✅ | （extras 仓）refactor: import the public api surface instead of core internals |
| T5-03 | P0 | T5-00 | astrbot/api/content | 新建 content 模块 + `is_text_part` / `is_image_part` | 缺席时导入不报错、判定返回 False | pytest | 是 | ✅ | feat(api): expose content part types |
| T5-04 | P0 | T5-00 | astrbot/api/runtime | 新建 runtime 模块 + 3 个运行时工具 | 缺席时降级语义如契约 §3.0.2 | pytest | 是 | ✅ | feat(api): expose runtime helpers |
| T5-05 | P1 | T5-00 | astrbot/api/embedding | 新建 embedding 模块 + `is_embedding_provider` | 缺席时导入不报错 | pytest | 是 | ✅ | feat(api): expose embedding provider type |
| T5-06 | P0 | T5-02..05 | tests/maintained/ | 三模块测试 + 插件侧 import 扫描测试 | 全绿且覆盖降级分支 | pytest | 否 | ✅ | test(api): cover phase 5 api additions |
| T5-07 | P0 | T5-06 | 实例插件目录 | 仓 → 实例同步 + 重载插件 + 验证加载 | 插件正常加载、无 ImportError | 重载后查端口/日志 | 否 | ✅ | （重启后复核通过，见 deploy-log.md） |
| T5-08 | P0 | T5-07 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ✅ | — |
| T6-00 | P1 | T5-08 | docs/maintained/tools.md | 写工具链规格（用法/退出码/边界） | 契约齐全 | 评审 | 否 | ✅ | docs(sdd): specify maintenance tooling |
| T6-01 | P1 | T6-00 | maintained/tools/check_drift.py | 漂移检测（实例 + 可选仓内） | 台账口径比对，退出码 0/1/2 | pytest + 真实实例实测 | 是 | ✅ | feat(tools): add check_drift |
| T6-02 | P1 | T6-00 | maintained/tools/apply_patches.py | 一键重打（默认预演，`--apply` 才写；先备份再写） | 源校验→备份→写回→复核 | pytest + 端到端注入漂移实测 | 是 | ✅ | feat(tools): add apply_patches |
| T6-03 | P0 | T6-01,02 | tests/maintained/test_tools_*.py | 24 项测试覆盖全分支 | 全绿 | pytest | 否 | ✅ | test(tools): cover drift detection and patch apply |
| T6-04 | P0 | T6-03 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ✅ | — |
| T7-01 | P1 | T6-04 | tests/maintained/test_manifest_guard.py | 回归护栏①：仓工作树↔台账自洽 + 台账守卫 | 全绿且当前即绿 | pytest | 否 | ✅ | test(maintained): guard manifest consistency and contents |
| T7-02 | P1 | T6-04 | tests/maintained/test_api_frozen.py | 回归护栏②：上游 api 相对 baseline 零改动 | 白名单=9 新增文件，其余零改动 | pytest | 否 | ✅ | test(maintained): freeze upstream astrbot/api against baseline |
| T7-03 | P0 | T7-01 | docs/maintained/{api-contract,design,proposal,tasks}.md | 文档对齐现实（14 处不一致） | 数字/清单/前置依赖自洽 | 目视+评审 | 否 | ✅ | docs(maintained): correct api-contract drift 等 |
| T7-04 | P0 | T7-03 | docs/maintained/project_rules.md, .gitignore | 自检正则收紧 + `.gitignore` 锚定与去重 | 自检 grep 实测为空 | 命令 | 否 | ✅ | docs(maintained): tighten secret-scan regex / chore: anchor ignores |
| T7-05 | P1 | T7-03 | provider/entities.py 等 4 文件 + api/media | **P4** `IMAGE_CAPTION_MARKER` 下沉 core，4 处改引 + api/media 改 resolve（零行为变化） | 值不变、上游测试**无新增失败（17→17）**、台账同步 | pytest+台账 | 是 | ✅ | refactor(core): centralize image caption marker constant |
| T7-06 | P1 | T7-05 | tool_loop_agent_runner.py | **P5** `_proactive_delivery_deferred` 提升为正式字段（零行为变化） | 默认值与 getattr 兜底一致 | pytest+台账 | 是 | ✅ | refactor(core): declare proactive delivery deferral attribute |
| T7-07 | P1 | T7-06 | respond/stage.py, context_utils.py, aiocqhttp_message_event.py | **P7** 门禁静默 return 补 logger.debug（零行为变化） | 仅新增日志、控制流不变 | pytest+台账 | 是 | ✅ | refactor(core): log silent gate returns at debug level |
| T7-08 | P1 | T7-07 | tool_loop_agent_runner.py 等 4 文件 | **P8** 魔法数字提取具名常量（值逐字节不变） | 逐项人工比对数值一致 | pytest+台账 | 是 | ✅ | refactor(core): name magic numbers in agent/turn paths |
| T7-09 | P0 | T7-08 | D:/asbot_extras | 插件删死导入/死变量 + 新增只读 enhance api-status 自检 | 插件 183+ 测试全绿、命令只读 | pytest+重载 | 否 | ✅ | refactor(plugin): drop unused api import and flag / feat(plugin): add read-only api capability self-check command |
| T7-10 | P0 | T7-09 | 实例 core | 部署（apply_patches --apply）+ 重启 + 只读信号复核 | check_drift 双段 NO DRIFT、三端口在听、active_reply.enable 仍 false | 命令+用户实操 | 否 | ✅ | （实例侧，见 deploy-log.md） |
| T7-11 | P1 | T7-10 | CHANGELOG.md | 补阶段 6/7 条目、修正测试项数、22→31 注记 | 与台账/测试实测一致 | 目视 | 否 | ✅ | docs: update changelog for phases 6-7 |
| T7-12 | P0 | T7-11 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ✅ | —（依赖它的 T7-13/14/15 均已完成 ⇒ 视为门禁已过；**无独立对话记录存证**，据现状补记） |
| T7-13 | P0 | T7-12 | docs/maintained/{project_rules,proposal}.md | **重定项目定位**：面向社区开源的轻量级/高灵活度/集成增强版；核心价值=补官方缺的底层扩展 API | 两份文档均有定位节且互相一致 | 目视 + 评审 | 否 | ✅ | docs: restate the project positioning for community use |
| T7-14 | P0 | T7-13 | docs/maintained/inventory.md | **β hook 时序登记为核心架构优化**：保留现状、坚决不改回上游、严禁上游合并时覆盖 | P11 有明确标记；`project_rules.md` §5 列为合并红线 | 目视 | 否 | ✅ | docs: protect the beta hook-timing optimisation from upstream merges |
| T7-15 | P0 | T7-13 | docs/maintained/{project_rules,api-contract}.md + astrbot/api/** | **api 面文档门槛**（§9）：模块 docstring/`__all__`/逐符号 docstring/常量 `#:` 注释；禁止野路子公开名 | 机械测试 `test_api_doc_gate.py` 全绿；已修 `permissions._EXECUTION_POLICY_UNAVAILABLE` 与 `turns._logger` | pytest + 评审 | 否 | ✅ | feat(api): enforce the public-surface documentation gate |
| T7-90 | P2 | — | — | **⛔ Blocked（转公开 / 脱敏 / 对外材料）**<br>**解除条件**：本阶段**存量治理与重构完成、测试全绿**后才启动。<br>**Blocked 理由**：当前注意力全部集中在**代码攻坚**；过早对外会锁死尚在重构的公开面。<br>**明确不做（在解除前）**：转公开、脱敏、对外材料同步、`README_MAINTAINED.md` 措辞调整。 | 解除条件达成且用户确认 | 用户确认 | — | ⛔ Blocked | — |
| T7-91 | P3 | T7-90 | README_MAINTAINED.md 等对外材料 | 把新定位同步到对外材料 | 与定位一致 | 目视 | 是 | ⛔ Blocked（随 T7-90 一并解除） | — |


## 阶段 8 · 存量治理与重构（代码攻坚 —— T7-90 的解除前置）

> 2026-10-10 定调：注意力全部集中在代码攻坚；**不做**脱敏、不做对外材料（随 T7-90 一并 Blocked）。

| 编号 | 优先级 | 前置依赖 | 涉及文件 | 工作内容 | 完成标准 | 验证方式 | 可否并行 | 状态 | 提交信息 |
|---|---|---|---|---|---|---|---|---|---|
| T8-01 | P0 | — | tests/, conftest.py, maintained/p11_deviations.py | **P11 定型**：α 9 项标 `xfail(strict)`（设计使然的预期失败）；β 8 项标 `xfail(strict)` 并登记为核心架构优化、保留现状——给"测试全绿"一个明确定义 | 套件输出 = maintained 全绿 + 上游 `170 passed, 17 xfailed`，无未解释的红 | pytest | 否 | ✅ | docs(maintained): classify the 17 upstream deviations as expected failures / test(maintained): mark known upstream deviations as strict xfails / docs: update changelog and test inventory for phase 8 |
| T8-01R | P1 | T8-01 | docs/maintained/hook-timing-impact.md | **β 影响面排查**（本机插件 / 官方插件市场 / 判据）+ `hook_timing_mode` 开关（**初版**默认 `enhanced`，可选 `legacy`；**2026-10-18 T8-16 起默认改为 `legacy`**）的**接入点规划**；**本轮只出报告、不写 core 代码**，开关实施并入 T8-07 | 报告含影响清单与接入点，用户确认 | 评审 | 是 | ✅ | docs(maintained): report hook-timing impact and plan the mode switch |
| T8-10 | **P0（安全）** | T8-07 | `astrbot/core/code_delivery_policy.py:38-78（**2026-10-16 订正**：旧记行号已失效，误放行/授权分支实况 **70–77**，「然后|并|再|并且」在 **72**；38–78 为禁区整体）` | **execution_denial 误放行（提权风险）**：输入「文档里写：先编译，再运行」被判为**授权执行**（`:80` 的 `然后\|并\|再\|并且` 分支无主语约束 → 引用/转述文档即等于授权）；修复需给该分支加主语约束。一并评估 `SAFETY_REFUSAL_PATTERN`（`:19-27`）的**漏判**（「我不能帮你写病毒/木马」不在风险词表 → 真拒答被送去 repair）与**误报**（纯技术说明被判拒答 → 跳过修复，用户拿到不完整代码）<br>**2026-10-17 取证与方案（用户已批准）**：实测 18 例，误判 9 例 ——**误放行 4**（转述文档/教程/代码被判为授权）、**漏判 5**（「麻烦你帮我运行一下」「跑一下」「启动」被拒）。`SAFETY_REFUSAL_PATTERN` 另有**漏判 2**（「我不能帮你写病毒」「我没法协助编写攻击脚本」未识别为真拒答）、误报 0。**方案 D（模式化）**：① 新增 `provider_settings.execution_gate_mode`，默认 **`legacy`** = 上游 admin-only；可选 `strict` = 现行执行意图判定；落 `default.py`（默认值+schema）与 `util.py` EXECUTION 分支分流；⚠️ 默认改 legacy 后 `test_python_tools.py` 的 **11 项红实测转绿**（闸门仿真 match=True）。② strict 模式内加「转述标记 + 写/说/是/：」排除规则，实测 4 例误放行全修、**零新增漏判**；漏判 5 例作为 strict 的已知代价写进 hint，用户可切回 legacy。③ **零 dashboard 改动**（用户裁决 A：仅走 schema） | 默认 legacy 与上游一致且 11 项红转绿；strict 下转述不再被判为授权；α 组测试口径同步复核 | pytest | 否 | ✅ | docs(maintained): record the T8-10 triage and the mode-based plan / feat(core): add the execution gate mode setting defaulting to upstream behaviour / feat(core): let the execution gate fall back to the upstream admin check / fix(core): stop treating quoted documents as execution consent / test(maintained): expect quoted documents to be denied / test(maintained): pin the new quoting marker regex / test(maintained): cover both execution gate modes / chore: sync the manifest hashes for the execution gate mode / style(core): keep the quoting marker regex on one source line |
| T8-11 | P2 | T8-07 | `cron/manager.py:465`、`astr_agent_tool_exec.py:572` | **cron 与子代理（background）路径未透传 `hook_timing_mode`**：这两处构造 `MainAgentBuildConfig` 时未读 misc（`tool_schema_mode` 同样未读），故该场景下恒为 `enhanced` | 两条路径也读 misc 并传入，legacy 在 cron / 后台任务场景同样生效 | pytest | 是 | ✅ | docs(maintained): document the cron and sub-agent hook timing passthrough / feat(core): read the hook timing mode for cron and background wakes / chore: register the cron and sub-agent wake paths in the manifest / test(maintained): cover hook timing passthrough for cron and background |
| T8-09 | P2 | T8-01R | 实例长期记忆插件（源码在私有仓，本仓不落） | **观察项**（负责人指示：**只出结论不改代码**）：其反射入库是否早于内容安全审计 | ✅ **结论：不存在入库早于审计**（priority 降序 + 审计原地改写同一 `LLMResponse` + 拦截 `stop_event()` 掐断后续钩子 + 重试不经事件钩子）。**本 fork 无需改动**；真实风险改写为覆盖盲区（私聊零审计 / 用户输入零审计 / 输出侧只剩 LLM 审查），均属插件侧。落盘 `docs/maintained/livingmemory-audit-order.md`，含「记忆钩子缺 `is_chunk` 判断」附带发现（**仅记录不修**） | 实测 + 评审 | 是 | ✅ | docs(maintained): report the memory storage versus safety audit order |
| T8-02 | P0 | T8-01 | P10 区域 | **手写正则安全判定**：先补测试把当前行为钉死（误判容限显式化），再谈优化 | 行为被测试覆盖 | pytest | 否 | ✅ | docs(maintained): record the code delivery policy regex behaviour / test(maintained): pin the code delivery policy regex behaviour / docs: update changelog and test inventory for T8-02 |
| T8-03 | P0 | T8-02 | P2 区域 | **core 反向硬依赖插件目录名（2 处）→ 注册表/钩子化**；完成后解锁"插件名守卫测试"（严格版） | core 内零插件目录名 | grep + pytest | 否 | ✅ | docs(maintained): document the plugin capability lookup contract / refactor(core): find proactive capabilities by contract instead of plugin name / chore: sync manifest hashes for the capability lookup / test(maintained): cover capability lookup and the plugin name guard / docs: update changelog and test inventory for T8-03 |
| T8-04 | P1 | T8-03 | P3 区域 | **工具名硬编码白名单 → 工具自声明**（执行类 / 轻量主动类） | 白名单不再写死在 core | 评审 + pytest | 是 | ✅ | docs(maintained): document the tool capability declaration contract / feat(core): let execution tools declare themselves / feat(core): let proactive tools declare themselves with a config fallback / chore: register the tool schema and sync manifest hashes for T8-04 / test(maintained): cover tool capability declarations / docs: update changelog and test inventory for T8-04 |
| T8-05 | P1 | T8-04 | P6 区域 | **权限双模型统一入口**（负责人 2026-10-12 拍板 **A 语义**：仅统一入口/命名，**判定强度逐点保持现状、行为零变化**；明确**不合并成 AND**，避免扩散 `execution_denial` 的已知误判） | 单一判定入口 | pytest | 是 | ✅ | docs(maintained): specify the single tool permission entry / refactor(core): funnel tool permission checks through one entry / test(maintained): cover the single tool permission entry / chore: sync manifest hashes for the permission entry / docs: update changelog and test inventory for T8-05 |
| T8-13 | P2 | T8-05 | `astrbot/core/tools/computer_tools/{python,shell}.py`、`astrbot/core/code_delivery_policy.py` | **本次观察中新发现（不属 T8-05 范围，⛔ 严禁顺手改）**：早先回合把 `python.py` / `shell.py` 的闸门换成 `execution_denial` 后，该函数**无条件**读 `event.get_sender_id()`，而**未改动的上游测试** `tests/unit/test_python_tools.py` 的事件桩没有该方法 ⇒ **11 项 AttributeError 失败**；已用临时工作树在改动前提交 `5580e9595` 复跑，**前后同为 11 失败**，非本次引入。提示真实脆弱性：非标准消息上下文会抛异常而非返回拒绝串。待单独评估修复方向<br>**2026-10-15 取证与裁决**：失败链 `util.py:108 → code_delivery_policy.py:48`（只判真值、不判方法是否存在）；真正引入点是更早的「admin-only → 执行意图判定」加固（非 T8-05，T8-05 只换入口名）。**真实场景核查**：`get_sender_id` 全仓只在基类 `AstrMessageEvent:203` 定义一次、无子类重写，17 个平台事件类 + `CronMessageEvent` 全部继承 ⇒ 真实运行必然带该方法 ⇒ 兜底为**零行为变化**；仅测试桩/伪造上下文受影响（崩溃 → 拒绝，fail-closed）。**裁决：只做异常兜底，不登记为预期偏差、不退回上游闸门语义**；落点 `util.py`，`code_delivery_policy.py` 38–78（T8-10 禁区）**零触碰**。兜底后 `test_python_tools.py` 仍 11 红（错误由 AttributeError 变为断言不匹配），属预期，且不在 295+17 跟踪口径内 | 单独排期决策 | pytest | 是 | ✅ | docs(maintained): record the T8-13 triage and the fallback decision / fix(core): deny execution when the sender cannot be identified / test(maintained): cover the execution level with an unidentifiable sender / chore: sync the manifest hash for the tool permission entry / fix(core): read the message id defensively when logging the execution entry / test(maintained): cover the execution entry with a minimal event stand-in / chore: sync the manifest hash for the tool permission entry |
| T8-14 | P2 | T8-10 | `astrbot/core/code_delivery_policy.py`（`SAFETY_REFUSAL_PATTERN`）；`astrbot/core/agent/runners/tool_loop_agent_runner.py` **只引用该常量、不改其代码** | **真拒答漏判**：T8-10 取证时实测 ——「我不能帮你写病毒或木马」「这个我没法协助你编写攻击脚本」**未被识别为真拒答**（「病毒/木马」不在风险词表、「没法」不在否定词表）⇒ 被当成「代码未写完」而**触发补生成**，等于逼模型重写它刚拒绝的内容。修复方向：**只扩正则词表** —— 风险词加 病毒/木马/恶意软件/勒索/漏洞利用/窃密/赌博/毒品，否定词加 没法/拒绝/不便/不宜/不应该/不做/不写/不生成；**不动 runner 代码**（零 β 风险）。误报代价（少补一次代码）**远轻于**漏判代价（逼模型产出违规内容），故宁可放大召回，并配一批误报测试钉住边界 | 真拒答不再触发补生成；正常技术回答不误判 | pytest | 是 | ✅ | fix(core): recognize more genuine refusals in the safety pattern / test(maintained): pin the widened refusal pattern / test(maintained): cover refusal recall and false positives / chore: sync the manifest hash for the refusal pattern |
| T8-15 | **P0（安全/兼容）** | T8-10 | `astrbot/core/code_delivery_policy.py`（`apply_execution_policy` + 转述标记词表） | **T8-10 遗漏点（用户实测发现）**：执行管控实际有**三处** —— ① `apply_execution_policy` 工具过滤 + 系统提示注入（`astr_main_agent.py:1680` 每请求调用）② util.py 调用时闸门（已模式化）③ ①注入的系统提示。T8-10 只模式化了 ② ⇒ legacy 下工具**仍被移除**、提示**仍被注入**（日志实证：`Execution policy ... allowed=False removed=astrbot_execute_shell`），模型根本没机会调用 ⇒ 「帮我运行这段代码: print(123)」未执行。另：转述标记词表里的「这段」**误伤**常规请求（「帮我运行这段代码：print(123)」被判为转述）。修复：① `apply_execution_policy` 读取 `execution_gate_mode`，legacy 直接放行（不删工具、不注入提示）；② 词表去掉「这段」（「这段话的意思是」仍由「意思是」覆盖） | legacy：管理员消息可实际执行、工具不被移除、无注入；strict：转述仍拒绝且「帮我运行这段代码：」放行 | pytest | 是 | ✅ | docs(maintained): register the missed execution policy enforcement as T8-15 / fix(core): let the execution policy filter honour the gate mode / test(maintained): cover the execution policy filter in both modes / test(maintained): pin the strict-mode tool filtering / chore: sync the manifest hash for the execution policy / docs(maintained): record the alpha deviation revert under P11 / chore: drop the alpha deviations reverted by the gate mode / test(maintained): expect no alpha deviation after the gate mode revert |
| T8-16 | **P1（N3 增强模式骨架）** | T8-15 | `astrbot/core/config/agent_runner.py`（`HOOK_TIMING_MODE_DEFAULT`）、`astrbot/core/agent/runners/tool_loop_agent_runner.py`（构造处记录当前模式）、`astrbot/api/runtime/__init__.py`（兜底值）、`astrbot/core/config/default.py`（schema hint）、`maintained/p11_deviations.py`（β 组登记） | **双模式定调落地**：① 钩子时序默认 `enhanced` → **`legacy`**（默认回到上游行为，enhanced 仍可通过开关开启，**代码路径不删** ⇒ 不违反 β 红线）；② **传播遗漏**：`set_hook_timing_mode` 原本只在 `internal.py:106`（主对话）调用，定时（`cron/manager.py:464`）与后台（`astr_agent_tool_exec.py:576`）不更新全局 ⇒ 插件经 `astrbot.api.runtime.hook_timing_mode()` 读到残留值 ⇒ 改到 **runner 构造处（runner.py:418）统一记录**，一处覆盖全部构建路径（含将来的新路径）；③ API 层兜底值随默认改为 legacy | 默认 legacy 与上游一致；定时/后台也记录正确模式；β 组 8 项预期转绿 | pytest | 是 | ✅ | docs(maintained): register the enhancement mode skeleton as T8-16 / feat(core): default the hook timing to the upstream behaviour / fix(core): record the hook timing mode for every build path / feat: align the plugin-facing hook timing default and hint / fix(api): resolve the enhanced hook timing constant by name / test(maintained): expect the legacy hook timing default / docs(maintained): record the beta deviation revert under P11 / chore: drop the beta deviations reverted by the timing default / test(maintained): expect no deviation after the timing default revert / chore: sync the manifest hashes for the timing mode / docs(maintained): mark the dual-mode conflicts as resolved |
| T8-17 | P2 | T8-16 | `docs/maintained/{api-contract,hook-timing-impact,inventory,roadmap}.md` | **文档一致性核对**：默认行为已改两处（执行闸门 legacy、钩子时序 legacy）、上游偏离已归零（17→0），但文档里仍有多处按旧默认写的表述与失效行号 —— 已扫到 `api-contract.md:83/87`（hook_timing_mode 默认 enhanced）、`hook-timing-impact.md:13/106/135/144/173`（默认 enhanced）、`inventory.md:160/252`（“17 项失败”）、`inventory.md:172`（行号 1857 待核） | 文档表述与代码实际行为一致；行号引用可核对 | 人工核对 + pytest | 否 | ✅ | docs(maintained): register the documentation consistency audit / docs(maintained): correct the hook timing default in the API contract / docs(maintained): update the hook timing default across the impact doc / docs(maintained): refresh the deviation counts and a stale line reference / docs(maintained): finish the deviation count and default refresh |
| T8-06 | P1 | T8-05 | P9 区域 | **maintenance fail-open → warning**；`uninstall_plugin` 补闸门 | 更新/安装/卸载三入口闸门齐备 | 实测 + pytest | 是 | ✅ | docs(maintained): document the maintenance protection gate / fix(core): warn instead of silently skipping the maintenance check / feat(core): gate plugin uninstalls behind the maintenance list / chore: sync manifest hashes for the maintenance gate / test(maintained): cover the maintenance gate and uninstall force / docs: update changelog and test inventory for T8-06 |
| T8-07 | P0 | T8-01R | `config/agent_runner.py`、`config/default.py`、`astr_main_agent.py`、`.../agent_sub_stages/internal.py`、`agent/runners/tool_loop_agent_runner.py`、`api/runtime/__init__.py` | **落地 `hook_timing_mode` 开关**（**初版**默认 `enhanced` / 可选 `legacy`；**2026-10-18 T8-16 起默认改为 `legacy`**）：misc 配置项 → 沿 `tool_schema_mode` 既有链路传参 → runner 在 **1130** 加 legacy 分支 → `astrbot.api.runtime` 只读暴露。**只在「上游有对照的路径」延后（仅 1130）；fork 独有路径（977 / 1325）保留优化；1093 一行不动** | legacy 在有对照路径上逐点等于上游；fork 独有路径保留优化；maintained 全绿、上游 `170 passed + 17 xfailed` 不变、台账 4 条哈希同步、双端 31/31 | pytest + drift + 用户重启复核 | 否 | ✅ | docs(maintained): specify the hook timing api and settle the legacy scope / feat(core): add the hook_timing_mode runner setting / feat(core): plumb hook_timing_mode into the main agent build / feat(core): defer the completion hook in legacy mode / feat(api): expose the current hook timing mode / chore: sync manifest hashes / test(maintained): cover both hook timing modes |
| T8-12 | P1 | T8-07 | 🟡 4 文件 | **拆分重写**（含 runner 拆分；原 T8-07 内容，因开关任务插队而顺延）；**β 的 hook 完成时序优化必须原样保留**（P11 红线） | 行为等价、全量测试全绿、P11 复核无回退 | pytest + P11 复核 | 否 | ✅ | 见 `t8-12-retrospective.md` §1（共 44 个提交，`57bacfc09` → `4c2d8acc9`） |
| T8-08 | P0 | T8-07 | — | **阶段门禁：停下汇报 ≤10 行，等确认** → 之后才回到 T7-90 评估 | 已汇报且确认 | 对话记录 | 否 | ✅ | —（2026-10-12 收工验收：已汇报且确认；T7-90 仍 Blocked） |

> **定位变更提示（2026-10-10）**：项目已重定位为「面向社区开源的集成增强版 AstrBot」（见 `project_rules.md` 置顶节）。
> T7-90（转公开）已正式 **Blocked**：待阶段 8（存量治理与重构）完成、测试全绿后启动。
