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
| `T7-` | 阶段 7 发布 |

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
| T1-05 | P0 | — | GitHub | 建两个私有仓 `astrbot-maintained` / `astrbot-extras`（autoInit=false） | 两仓存在且为空 | GitHub 页面 | 是 | ⬜ 阻塞（MCP 无 repo 写权限，需 PAT 或手动建） | （无提交） |
| T1-06 | P0 | T1-04, T1-05 | refs | 显式 refspec 推分支 + 2 个 tag（禁 `--all`/`--mirror`） | `git ls-remote origin` 含 3 ref、无 master | 命令 | 否 | ⬜ 阻塞 | （push） |
| T1-07 | P1 | T1-04 | docs/maintained/proposal.md | 写 proposal（含"不做"与验收） | 11 节齐全 | 目视 | 否 | ✅ | docs(sdd): add proposal for maintained AstrBot fork |
| T1-08 | P1 | T1-07 | docs/maintained/design.md | 写 design（含对应关系表与降级方案） | 13 节齐全 | 目视 | 否 | ✅ | docs(sdd): add design and compatibility boundary |
| T1-09 | P1 | T1-08 | docs/maintained/tasks.md | 写任务表 | 编号规则生效 | 目视 | 否 | ✅ | docs(sdd): add phased task table |
| T1-10 | P1 | T1-09 | docs/maintained/project_rules.md | 写执行规则（六铁律） | 六铁律逐条可指认 | 目视 | 否 | ⬜ | docs(sdd): add project rules (six invariants) |
| T1-11 | P1 | T1-04 | NOTICE, README_MAINTAINED.md | AGPL §13 声明 + fork 说明 | 含上游 URL / 基线 sha / 许可 | grep | 是 | ⬜ | docs: add AGPL section 13 notice and fork README |
| T1-12 | P1 | T1-04 | .gitattributes, .gitignore | LF 归一化 + 私有代码黑名单（仅末尾追加） | 上游原有行未改 | `git diff` | 是 | ⬜ | chore: add gitattributes and hardened gitignore |
| T1-13 | P2 | T1-04 | maintained/** | 从归档仓只读复制台账与校验器 | 两端 sha256 一致 | sha256sum 比对 | 是 | ⬜ | chore: import maintenance tooling snapshot from archived astrbot_local |
| T1-14 | P2 | T1-04 | CHANGELOG.md | 初始化变更台账 | 含"阶段 1 基线：3c7adafa" | 目视 | 是 | ⬜ | docs: initialize maintained changelog |
| T1-15 | P0 | T1-10..14 | 全仓 | 私有代码残留扫描 + 换行/体积体检 | 三条 grep 全空 | 见 project_rules §6 | 否 | ⬜ | （无提交） |
| T1-16 | P0 | T1-15 | — | **阶段门禁：停下汇报 ≤10 行，等用户确认** | 已汇报且确认 | 对话记录 | 否 | ⬜ | — |

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
| T3-09 | P0 | T3-08 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ⬜ | — |
| T4-01 | P0 | T3-09 | core 实例 | 备份 → 恢复 26 补丁 + 6 api 文件 → SHA 校验 | 台账 28/28 一致、capabilities 全 True | 实测 | 否 | ✅ | （实例侧操作，见 docs/maintained/deploy-log.md） |
| T4-02 | P0 | T4-01 | 实例运行 | 启动 AstrBot，确认插件加载成功 | 日志无 ImportError、机器人可响应 | 实测日志 | 否 | ✅ | 已核验：PID 211524 监听 6199/6185，插件 WebUI 6196 在听 → 插件已加载 |
| T4-03 | P0 | T4-02 | 插件配置 | **铁律 6**：`active_reply.enable` 置 `false`（防调试误发） | 重启后仍为 `false` 且逐项语义比对只差该 1 项 | 目视 + 语义比对 | 否 | ✅ | （实例侧，见 deploy-log.md） |
| T4-04 | P0 | T4-03 | — | **阶段门禁：停下汇报 ≤10 行，等确认** | 已汇报且确认 | 对话记录 | 否 | ⬜ | — |
| T5-01 | P1 | T4-01 | 私有仓 extras | 3 处私有 import → 公开 API + try/except 降级 | 插件无顶层私有 import | grep + 实测 | 否 | ⬜ | 待定 |
| T6-01 | P2 | T5-01 | maintained/tools/ | check_drift / apply_patches 工具 | 一键校验与重打可用 | 实测 | 是 | ⬜ | 待定 |
| T7-01 | P1 | T6-01 | NOTICE / CHANGELOG / tag | CHANGELOG、§13 README、打 tag、转公开 | 仓库公开且 §13 义务满足 | 目视 | 否 | ⬜ | 待定 |
