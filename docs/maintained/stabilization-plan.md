# 稳定版基线方案（v4.28.2+mtn）

> 目标：先交付一个**可复现、可验证、可回滚**的基础版本，再在其上继续迭代。
> 判定标准不是"功能多"，而是三条同时成立：
> **① 仓库里的版本 = 实例跑的版本；② 用户可见的功能都有入口；③ 已知偏差全部登记、可观测。**
>
> 编写时间：2026-11-04 · 基线 `baseline/v4.28.2`（3c7adafa）· HEAD `39ff2d284`

---

## 1. 现状快照（本次实测）

| 项 | 数值 | 说明 |
|---|---|---|
| 维护版测试 | **526 passed / 3 skipped** | `tests/maintained/` |
| 上游测试 | **2949 passed / 2 failed / 6 skipped** | 2 项失败 = 未登记的偏差（见 R2） |
| ruff check / format | 全绿 / 536 文件已格式化 | 仓库级 |
| 台账 | **56 条**，全部 `.py` | 有 4 个非 `.py` 改动**未登记**（见 R1） |
| 与上游差异 | 60 个 core 文件（25 新增/35 修改） | +5709 / −544 |
| 落后上游 | v4.29.0–.4，240 提交 | 追上游不在本方案范围内 |
| 私有代码残留 / CRLF | 0 / 0 | 通过 |

---

## 2. 病根归纳（10 类，风险都从这里长出来）

| # | 病根 | 表现 |
|---|---|---|
| C1 | **两套配置 schema 并存**（`CONFIG_METADATA_2` 只喂校验与 legacy 接口，前端只用 `_3`/`_3_SYSTEM`），新项默认往老的那套加 | 新配置项没有 GUI 入口 |
| C2 | **用模块级全局表达运行模式** | 多机器人/多档案交叉时读到别人的值 |
| C3 | **核心直接读第三方插件私有 extra**（`_enhance_*`） | 插件改名即静默退化 |
| C4 | **能力解析靠字符串模块路径 + 缺省静默降级** | 上游移走模块 → 功能消失但无报错 |
| C5 | **同一策略在多处复制**（gate 判定 ×3） | 加第三种模式必漏改 |
| C6 | **守卫测试只校验"条数/哈希"，不校验"集合完整性"** | 新文件漏登记 / 版本标记丢失无人发现 |
| C7 | **偏差登记表被清空后没有回归入口** | 新偏差静默堆积 |
| C8 | **热路径日志未分级** | 群活跃时日志被业务细节刷屏 |
| C9 | **多维数据用分隔符编码成单值**（`a|b|c`、`type:plugin`） | 统计无法正确聚合 |
| C10 | **部署是文件副本，无构建溯源** | 说不清实例跑的是哪个提交 |

---

## 3. 风险登记与处置

### P0 — 发布阻断（版本不一致 / 用户可见缺口）

#### R1 台账漏登记 4 个文件，部署会漏

- **证据**：`git diff baseline..HEAD -- astrbot/` 有 60 个文件，台账 56 条且**全部是 `.py`**。未登记：
  `builtin_stars/bot_info/{_conf_schema.json,metadata.yaml}`、`builtin_stars/tool_react/{_conf_schema.json,metadata.yaml}`。
- **根源**：C6 —— 台账按 `.py` 惯例维护，`test_manifest_guard` 只断言"条数 == 56 + 哈希一致"，
  没有"**改动集合 ⊆ 台账**"这条断言；`apply_patches.py` 只碰台账内文件。
- **后果**：新实例/重装后，两个内置插件的设置项**没有 GUI 表单**（`_conf_schema.json` 缺失），
  能力退化为代码默认值；`check_drift` 也不会报（不在名单里，视而不见）。
- **治本**：台账纳入这 4 个文件；`test_manifest_guard` 增加集合断言：
  `set(git diff baseline..HEAD -- astrbot/) ⊆ set(manifest)`，失败时打印差集。
- **验证**：① 新断言在补登记前红、补后绿；② 干净实例跑 `apply_patches --apply` 后 4 个文件存在；
  ③ `check_drift --check-repo` 仍 NO DRIFT。

#### R2 上游 2 项测试失败且未登记（P11 空表）

- **证据**：`tests/unit/test_agent_runner_config.py` 2 项失败，原因是我们在 `agent_runner.config.misc`
  多了 `hook_timing_mode` / `lightweight_proactive_tools`，上游用**整字典相等**断言。
- **根源**：C7 —— α/β 回退后 P11 清空，之后新增的默认键无人登记，`xfail(strict)` 的报警机制处于失效状态。
- **后果**：以后上游改这段，我们**分不清**"我们的偏差"还是"上游改了预期"，回归不可见。
- **治本**：两项登记进 `maintained/p11_deviations.py`，并在 `inventory.md` §4 写明规则：
  "凡新增 `agent_runner` 默认键，必须同时登记该文件的偏差项"。
- **验证**：上游套件应变成 `2 xfailed, 0 failed`；**反证**：临时改一个默认键名 → 出现 `XPASS(strict)` 失败，
  说明告警真的活着。

#### R3 配置项缺 GUI 入口 / 缺类型校验

- **证据**（三个真实接口实测）：`direct_turn_quiet_sec`、`log_escape_message_newlines`
  只写在 `CONFIG_METADATA_2`；前端 `systemConfigApi`→`_3_SYSTEM`、`configProfileApi`→`_3`，
  且构建产物里搜不到 legacy `config/get`。`execution_gate_mode` 只在 `_3`，`_2` 没有它 ⇒ 无校验。
- **根源**：C1。
- **后果**：两项配置**只能改 JSON**；`execution_gate_mode` 手写错值不报错，静默当 strict 跑。
- **治本**：
  1. `direct_turn_quiet_sec`、`log_escape_message_newlines` 迁入 `CONFIG_METADATA_3_SYSTEM`；
  2. `execution_gate_mode` **同时**补进 `_2`（只为拿校验）与 `_3`（表单）；
  3. `_2` 里旧条目保留一版，避免旧客户端直接崩。
- **验证**：① 抓 `/api/v1/system-config` 断言两键在 `system_group`；② 抓档案接口断言 `execution_gate_mode` 在；
  ③ `PUT` 一个非法值，期望 4xx；④ 页面手点一次，确认表单可见（截图留档）。

### P1 — 基础版本可靠性（特定条件下会错）

#### R4 进程级全局模式状态

- **位置**：`config/agent_runner.py:258` `_CURRENT_HOOK_TIMING_MODE`，写入在
  `agent/runners/tool_loop_agent_runner.py:428`；公开为 `astrbot.api.runtime.hook_timing_mode()`。
  `utils/direct_turns.py:334` 的 `coordinator` 单例同理（`pipeline/scheduler.py:91` 每事件 `configure()`）。
- **根源**：C2 —— 用"最近一次构建"的全局值代表配置，与配置档案（per-bot）模型不匹配。
- **后果**：两个机器人模式不同且交叠时读到对方的模式；上游一旦做会话级配置即必坏。
- **治本**：模式值随 config 走，并在事件上留快照（`event.set_extra`）；
  `hook_timing_mode(event=None)` 有事件时读事件快照，无事件时读全局（兼容旧调用）；
  `coordinator.configure()` 改为从配置对象取值而非共享字段。
- **验证**：新增并发测试：两个不同 `quiet_sec`/`hook_timing_mode` 的上下文交错构造 runner，
  断言各自读到自己的值；`test_hook_timing_mode.py` 保持绿。

#### R5 核心反向依赖插件私有 extra

- **位置**（9 处）：`astr_main_agent.py:556-558`、`code_delivery_policy.py:104,107`、
  `image_input.py:127`、`tool_loop_agent_runner.py:888`、`astr_agent_run_util.py:167`、
  `pipeline/process_stage/follow_up.py:47`、`utils/direct_turns.py`（读 `_enhance_owned_*`）。
- **根源**：C3 —— 为让增强插件接管流程，核心直接认它的私有键；与项目自定的 P2 原则冲突。
- **后果**：插件改名/卸载/换实现 → 核心走 false 分支，图片丢、followup 退化，**全程无日志**。
- **治本**：新增 `astrbot/api/event/extras.py`，把键名收成常量并提供读写函数（**加法**，不动上游文件）；
  核心改为调用该模块；旧字面量保留一个版本兼容期。
- **验证**：单测三态（无键 / 有键 false / 有键 true）；`grep -r "_enhance_" astrbot/core` 归零。

#### R6 `_bridge` 静默降级

- **位置**：`api/_bridge.py:48` 能力表，含 `astrbot.core.astr_main_agent`（上游 master 已拆包）。
- **根源**：C4 —— 容错优先，缺能力只记一条 INFO。
- **后果**：升级后功能消失但服务照跑，问题要到用户投诉才发现。
- **治本**：能力表加 `required` 标记；必需能力缺失 → **ERROR 级 + 启动自检失败**（可用开关降级）；
  `apply_patches` 末尾自动跑一次能力自检。
- **验证**：临时重命名目标模块 → 断言启动 ERROR 且 `test_api_runtime` 仍通过（不崩、但吵）。

#### R7 `execution_gate_mode` 判定三处重复 + 无校验

- **位置**：`api/permissions/__init__.py:108`、`code_delivery_policy.py:233`、`computer_tools/util.py:102`。
- **根源**：C5。
- **后果**：加第三种模式时漏改任一处 ⇒ 工具列表与调用闸门不一致（一个放行一个拒绝）。
- **治本**：抽 `execution_mode(config) -> str` 单一入口（含白名单归一），三处改调用。
- **验证**：参数化测试 `legacy/strict/非法值`，断言三处判定一致；非法值有明确日志。

#### R8 版本标记无守卫

- **位置**：`astrbot/__init__.py` 的 `4.28.2+mtn1` 与 `__version_base__`。
- **根源**：C6 —— 没有任何测试断言 fork 标记存在。
- **后果**：合并上游时若冲突取了上游的 `4.28.2`，**没人发现**，从此无法区分官方版与维护版。
- **治本**：新增守卫测试：`__version__` 必须匹配 `^\d+\.\d+\.\d+\+mtn\d+$`，
  且 `__version_base__` 为纯 PEP 440 基础版本；发版时 `mtnN` 递增并写入 `README_MAINTAINED`。
- **验证**：故意改成 `4.28.2` → 测试红。

#### R9 热路径 INFO 日志

- **位置**：`direct_turns.py` 2 处（每回合必打）、`code_delivery_policy.apply_execution_policy`
  （**每请求一条** "Execution policy …"）、`context_utils.py` 的归因首条。
- **根源**：C8。
- **后果**：群活跃时 INFO 被业务细节淹没，真故障被冲走。
- **治本**：降 DEBUG；保留"每会话首条"或采样；`apply_execution_policy` 只在 **strict** 模式下打 INFO。
- **验证**：跑 20 条消息的压测脚本，期望 `INFO` 行数 ≤ 2；`strict` 模式仍能看到策略生效记录。

#### R10 部署无溯源

- **证据**：实例 `core/` **不是 git 仓库**（是副本），只能靠 `check_drift` 比对内容。
- **根源**：C10。
- **后果**：出问题时说不清"实例跑的是哪个提交、哪次构建"。
- **治本**：`apply_patches --apply` 成功时写入 `<实例>/core/data/maintained_build.json`
  （`commit`、`version`、`manifest_sha`、`applied_at`）；`instance_check` 读它并与当前 HEAD 比对。
- **验证**：部署后文件存在且 `commit` == `git rev-parse HEAD`；改一个文件后 `check_drift` 报漂移。

### P2 — 可维护性（发布后迭代，不进本次门禁）

| # | 位置 | 问题 | 治本方向 |
|---|---|---|---|
| R11 | `star/context.py:231` | `"|".join(plugins_for_provider(id)[:3])` 把**猜测**塞进单值 | 拆成 `plugin` + `attribution_method` + `candidates` 三字段 |
| R12 | `utils/control_tags.py:22` | 硬编码标签词表全局剥离 | 词表进配置/常量，只剥离本轮真的产出过的标签 |
| R13 | `utils/direct_turns.py:236` | `event.is_at_or_wake_command = True` 属性赋值式 duck typing | 走官方 API 或 `set_extra`，缺 API 时报错而非静默 |
| R14 | `default.py` `_2`/`_3` | 双 schema 长期并存 | 逐步把 `_2` 收成"仅校验用"并注明，禁止再往 `_2` 加展示项 |
| R15 | `plugin_attribution.py:148` | 扫 `*_config.json` 猜 provider 归属 | 改由插件显式声明（能力契约），扫描降为兜底 |
| R16 | `astr_main_agent.py`(1770) / `tool_loop_agent_runner.py`(1922) | 两个大文件 | **暂不做**：上游正在拆 agent，先拆会两边都对不上 |

---

## 4. 发布门禁（一条命令，退出码即结论）

新增 `maintained/tools/release_gate.py`，**只做编排**，不重复实现已有检查：

```
1. ruff check . && ruff format --check .
2. pytest tests/maintained -q            → 要求 0 failed
3. pytest tests --ignore=tests/maintained -q → 要求 failed == P11 登记数
4. check_drift.py --instance <dir> --check-repo → 要求 NO DRIFT
5. 台账集合完整性（R1 的断言，复用 test_manifest_guard）
6. 私有残留 / CRLF / .env 三条泄漏检查（复用 §6 自检）
7. 打印一行摘要：版本号、HEAD、测试数、漂移状态
```

任一步非零即**禁止发版**。全部通过后打印可复制的 `apply_patches` 命令。

---

## 5. 分期路线

| 阶段 | 内容 | 出口条件 |
|---|---|---|
| **S0 冻结** | 只允许 P0 改动；不再加新功能 | 台账、P11、配置入口三项闭环 |
| **S1 补基础** | R1–R3 + `release_gate.py` | 门禁一条命令全绿 |
| **S2 收隐蔽风险** | R4–R7（有可能触发行为错误的） | 新增并发/参数化测试全绿 |
| **S3 收尾发版** | R8–R10 + 文档（CHANGELOG、README_MAINTAINED） | 干净实例部署一次，`instance_check` 通过 |
| **S4 之后** | R11–R15 逐项；R16 不动 | 每项独立提交 + 测试 |
| **S5 追上游** | 目标 `v4.29.4`（**不追 master**） | 另立方案，本方案不含 |

---

## 6. 发版清单（每次发版照抄）

- [ ] `release_gate.py` 全绿（含漂移 NO DRIFT）
- [ ] `astrbot/__init__.py` 的 `+mtnN` 已递增，`README_MAINTAINED` 记录对应 commit
- [ ] `CHANGELOG.md` 有本次条目（沿用现有 Keep-a-Changelog 风格）
- [ ] 配置新增项：`_3`/`_3_SYSTEM` 有表单、`_2` 有校验；截图留档
- [ ] 台账条数与 `EXPECTED_ENTRY_COUNT` 一致，集合断言通过
- [ ] 干净实例 `apply_patches --apply` → 重启 → `instance_check` 通过 → `maintained_build.json` 已写
- [ ] 回滚演练：按备份目录里的 `RESTORE.md`（`apply_patches` 每次覆盖前生成，
      含逐文件 `state_before` 与 `sha256`）恢复一次，确认能回到上一个构建

---

## 7. 明确不做（防止范围蔓延）

- **不追上游 master**：`e9879c55f` 把 `astr_main_agent.py` 拆成 14 个模块的包，我们的 241+/244− 全在单文件里，追它等于重做 T8-12。
- **不拆两个大文件**（R16）：上游正在重构同一处，先拆会撞车。
- **不重写 `_bridge` 为 import 时强绑定**：会牺牲"上游覆盖补丁也不崩"的容错，等追完上游再说。
- **不动主动回复开关**：`proactive_must_remain_disabled` 恒 true。

---

## 8. 实施记录（2026-11-04，S1 已完成）

| 项 | 提交 | 落地内容 | 验证 |
|---|---|---|---|
| R1 | `b868dd6f9` | 台账补 4 个 `builtin_stars` 资产（56→60）；新增**集合完整性**断言 `test_every_touched_core_file_is_listed`；`base_ref` 移入台账 | 摘掉 1 条 → 测试红并点名该文件；恢复后绿 |
| R2 | `69f0efeee` | 新增 `config` 偏差组，登记 2 项上游精确字典断言；`inventory.md` P11 行同步 | 常规跑 `2 xfailed`；`--runxfail` 仍是 2 failed（证明不是消音） |
| R3 | `9938c9b91` | 两键迁入 `CONFIG_METADATA_3_SYSTEM`；`execution_gate_mode` 补 `_2` 校验；**四语言翻译**；`Settings.vue` 分组白名单加 `direct_turn_quiet_sec`；重建 dist | 浏览器实测两个标签都渲染、页面无原始 i18n key；`test_config_surface.py` 6 项 |
| R8 | `33512eb7e` | `test_version_marker.py`：`+mtnN`、`__version_base__`、pyproject 一致、README 一致 | 摘掉 `+mtn1` → 测试红 |
| R9 | `2e52fe137` | 三处热路径 INFO→DEBUG（`direct_turns` ×2、`apply_execution_policy` 的 legacy 分支） | `test_code_delivery_policy` / `direct_turns` / `hook_timing` 68 passed |
| R10 | `33512eb7e` + `d2e1c3a16` | `apply_patches` 写 `core/data/maintained_build.json`（commit/branch/version/manifest sha/时间） | 门禁的 `build stamp` 行；**发现并修复**了"内容已一致时提前返回不写戳" |
| 门禁 | `33512eb7e` + `9b125af7c` | `maintained/tools/release_gate.py`：lint / 台账 / 维护版 / 上游 / 漂移 / 构建戳，单命令单结论 | 首跑即抓出 2 个真实问题（见下） |

### R3 的三个隐藏条件（缺一个都看不到字段）

1. **元数据位置**：`_3_SYSTEM` 才有表单；`_2` 只做保存校验。
2. **页面白名单**：`Settings.vue` 的分组是硬编码数组，不在里面就不渲染。
3. **四语言翻译**：`_3` 会转成 i18n key，缺翻译就显示 `system_group.system.xxx.description`。

另有一条前置：`dashboard/dist` **不入仓**，改完必须重建并把 dist 同步进实例，否则浏览器跑的还是旧包。

### 门禁首跑的两次误报，都指向真问题

- `upstream FAIL`：把 `xfailed` 当成 `failed` 计数 —— 判定写错了，已改为"零 failed 且 xfailed == 登记数"。
- `build stamp FAIL`：实例戳落后 HEAD —— 工具在"内容已一致"时提前返回、不写戳，已修。

后一条恰好证明门禁有用：它抓的是"实例跑的不是你以为的那个构建"。

---

## 9. 实施记录（S2：R4 / R6 / R7）

| 项 | 提交 | 落地内容 | 验证 |
|---|---|---|---|
| R4-a | `f38702f14` | 时序模式随事件携带：`set_hook_timing_mode(value, event)` 写入 `_hook_timing_mode` 快照；`hook_timing_mode(event=None)` 有事件读快照、无事件读全局；runner 新增 `owner_event` 参数，主 agent 构建处传入 | 3 项新测试：快照优先、无 extras 的事件不崩、公开 API 接受事件 |
| R4-b | `32bdfba56` | 聚合窗口按会话隔离：`configure(quiet_sec, origin)`、`window_for(origin)`；`eligible()` / `collect()` 改读会话值；scheduler 传入 `unified_msg_origin` | 5 项新测试：两会话互不覆盖、未见过回退默认、单参数形式仍设默认、禁用会话不追踪、非法值不擦除 |
| R7 | `11c8886b5` | `execution_gate_mode(config)` 单一入口（含白名单归一，非法值→legacy）；三处调用点改为调用它 | 12 项参数化：两种合法值、9 种非法值、4 种坏 config |
| R6 | `11c8886b5` | `REQUIRED_CAPABILITIES` + `missing_required()`；`core_lifecycle.initialize()` 启动自检，缺必需能力记 ERROR 并点名 | 4 项新测试：必选集是注册表子集、完整核心无缺失、缺必需项被报、缺可选项不报 |

### 为什么 R4-a 只改"读"，不改"行为判定"

实际行为判定用的是 `runner.hook_timing_mode`（实例字段，`tool_loop_agent_runner.py:1083`），
本来就是每轮独立的。全局变量只被**上报接口**读，所以这次只是让上报值也跟着事件走，
没有触碰执行时序 —— 变更风险因此限制在"插件读到的值"这一层。

### R4-b 的关键：`eligible()` 与 `collect()` 也要改

只改 `configure()` 是不够的。`eligible()` 用 `self.enabled` 决定要不要追踪回合、
`collect()` 用 `self.quiet_sec` 算剩余等待，两处若继续读全局，就会得到
"按 A 的窗口决定要不要聚合，按 B 的窗口决定等多久"这种半隔离状态。

### R6 的一个设计取舍

`_bridge` 原本的容错原则是"缺能力就静默降级"，这对可选辅助函数是对的。
但 `turns.direct_turn` / `permissions.execution_policy` / `delivery.code_policy`
是本 fork 自有行为的载体，缺失等于补丁没打上。所以只把这 3 个标为 required，
其余 6 个保持静默降级 —— 一份名单，两种待遇，各自有理由。

