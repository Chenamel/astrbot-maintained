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
| T7-10 | P0 | T7-09 | 实例 core | 部署（apply_patches --apply）+ 重启 + 只读信号复核 | check_drift 双段 NO DRIFT、三端口在听、active_reply.enable 仍 false | 命令+用户实操 | 否 | ⬜ | （实例侧，见 deploy-log.md） |
| T7-11 | P1 | T7-10 | CHANGELOG.md | 补阶段 6/7 条目、修正测试项数、22→31 注记 | 与台账/测试实测一致 | 目视 | 否 | ✅ | docs: update changelog for phases 6-7 |
| T7-12 | P0 | T7-11 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ⬜ | — |
| T7-90 | P2 | — | — | **暂缓（用户决定）**：转公开 / 脱敏 / P2·P3·P6·P9·P10 | 用户另行决定 | — | — | ⏸ 暂缓 | — |
