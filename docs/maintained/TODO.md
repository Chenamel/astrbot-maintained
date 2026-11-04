# 交接文档 · 待办总表

> 生成时间：2026-11-04 18:30 · HEAD `bcb379da0` · 分支 `maintained/v4.28.2`
> 用途：compact 后新会话从这里接续。**读完本文再动手。**

---

## 0. 当前状态快照（已实测，勿凭记忆）

| 项 | 值 |
|---|---|
| HEAD | `bcb379da0` `docs: record the pre-release defect sweep...` |
| 分支 | `maintained/v4.28.2`（与远端同名） |
| 工作区 | **干净** |
| 未推送 | **23 个提交**（`origin/maintained/v4.28.2..HEAD`） |
| 版本 | `4.28.2+mtn1` |
| 台账 | **62 条**，`EXPECTED_ENTRY_COUNT = 62` |
| 维护版测试 | **602 passed / 1 skipped** |
| 上游测试 | **2949 passed / 2 xfailed**（2 项已登记 P11 `config` 组） |
| 实例 | 6185 监听中，构建戳 `5a1b38ba` |
| 发布门禁 | **七项全绿**（`RELEASE READY`） |

**实例路径**：`C:/Users/philia093/.astrbot_launcher/instances/83ca721d-26d2-4dd0-9932-ef9299d8829d`

---

## 1. 刚完成的（S1 + S2，共 23 个提交）

### S1：基础一致性（R1/R2/R3/R8/R9/R10）

| 风险 | 提交 | 内容 |
|---|---|---|
| R1 台账漏文件 | `b868dd6f9` | 补 4 个 `builtin_stars` 资产；新增**集合完整性断言** |
| R2 上游 2 项失败未登记 | `69f0efeee` | 新增 `config` 偏差组；`--runxfail` 仍 2 failed 证明不是消音 |
| R3 配置无 GUI | `9938c9b91` | 两键迁入 `_3_SYSTEM` + 四语言翻译 + `Settings.vue` 白名单 + 重建 dist |
| R8 版本标记无守卫 | `33512eb7e` | `test_version_marker.py` |
| R9 热路径日志 | `2e52fe137` | 三处 INFO→DEBUG |
| R10 部署无溯源 | `33512eb7e`+`d2e1c3a16` | `apply_patches` 写 `maintained_build.json` |
| 门禁 | `33512eb7e`+`9b125af7c` | `release_gate.py` 单命令单结论 |

### S2：隐蔽风险（R4/R5/R6/R7）

| 风险 | 提交 | 内容 |
|---|---|---|
| R4-a 全局模式串味 | `f38702f14` | 时序模式随事件携带（`_hook_timing_mode` 快照） |
| R4-b 聚合窗口串味 | `32bdfba56` | `configure(quiet_sec, origin)` + `window_for()` 按会话隔离 |
| R7 gate 三处重复 | `11c8886b5` | `execution_gate_mode(config)` 单一入口 |
| R6 静默降级 | `11c8886b5` | `REQUIRED_CAPABILITIES` + 启动自检 |
| R5 核心读插件私有键 | `ff399714b` | `astrbot/api/event/extras.py`，9 常量 + 10 读取器 |
| 发版前复查 | `4d49cd43e`+`5a1b38ba2` | **仪表盘版本标记缺失**（ERRO 2→0，启动 46s→24s） |

**完整记录**：`docs/maintained/stabilization-plan.md` §8–§11

---

## 2. 待办 · 按优先级

### P0：发版前必做（阻塞）

- [ ] **推送 23 个提交**。基础版目前只存在本机，这是唯一必须在发版前做的运维动作。
- [ ] **S3 发版动作**：
  - [ ] 版本 `4.28.2+mtn1` → `+mtn2`（同时改 `pyproject.toml`，`test_version_marker` 会校验一致）
  - [ ] `CHANGELOG.md` 汇总 S1/S2 内容
  - [ ] `README_MAINTAINED.md` 同步版本
  - [ ] 干净实例部署 + **回滚演练**（按 `optimization_backups/*/RESTORE.md`）
  - [ ] 重跑 `release_gate.py` 全绿

### P1：公开准备（用户已明确要做）

> 用户定位：**私有是过渡态，公开是既定目标**（`proposal.md:9` 已写明）。
> 但决定**保持私有仓以保留历史**，只把「扩展部分开发者指南」公开。

- [ ] **P1-1 文档数字纠正**（`docs/maintained/fork-advantages.md`，四个数字全错）：

  | 项 | 文档写 | 实际 |
  |---|---|---|
  | 台账条数 | 40 | **62** |
  | 测试数 | 384 | **602** |
  | 落后上游 | 163 | **240** |
  | 上游红测试 | "3 个，没有修" | **2 个，已登记 P11 + xfail 守卫** |

  最后一条要从"没修"改写为"登记 + 守卫"，这是**加分项**不是减分项。

- [ ] **P1-2 README 重写**（核心卖点埋太深）：
  现在 `README.md` 只有一句"`astrbot/api/**`：回合状态、交付策略…（上游未提供）"。
  应把 `fork-advantages.md` §3 那段提到开头：
  > `Context.llm_generate()` 与 `tool_loop_agent()` **都跳过 `on_llm_request` 钩子**，
  > 而人格/记忆/群上下文插件正挂在这个钩子上 ⇒ **基线上插件生成不了"带人格的话"**。
  > 本 fork 补了入口（构造 request → 跑钩子 → 调 provider），并附真实对照样本。

- [ ] **P1-3 补一份插件作者入门**（5 分钟能跑通）：现在只有 `api-contract.md`（301 行，面向实现者），
  缺"我想用 fork 能力，从哪开始"。建议落 `docs/maintained/plugin-quickstart.md`。

- [ ] **P1-4 决定公开形态**（三选一，见 §3 风险）：
  - A 现有仓库转公开（不可逆，历史全曝光）
  - **B 派生干净文档仓**（推荐：私有仓留历史，公开仓只放指南）
  - C 用 Release 附件（更新麻烦）

### P2：脱敏（仅在「公开整仓」时才需要）

> 若走 B 方案（只公开文档仓），**本节大部分可跳过**。

`docs/maintained/` 里仍有第三方插件点名（`roadmap.md` §4.2 已列清单）：

- `deploy-log.md` ×3（含私有插件配置路径）
- `future-ideas.md:59`（私有插件能力清单）+ `:105`（**实例 QQ 号 + 昵称**）
- `inventory.md:227`、`plugin-capability-lookup.md:10`、`plugin-pipeline-audit.md` ×2、`proactive-handoff.md:545`
- `project_rules.md:93,141-143`（隔离红线原文 + 自检命令）
- `proposal.md:100`
- **实例路径/用户名**：`debounce-in-shadow.md:188`、`hook-timing-impact.md:68`、`proactive-handoff.md:63,84`、`tests/maintained/README.md:18`

**代码侧已干净**：`maintained/proactive/*.py` 无硬编码（roadmap B0 ✅ 已完成）。
仅 `tests/maintained/` 两处测试夹具仍用真实号码（`test_quote_self_attribution.py:15`、`test_self_identity.py:24`），
属测试数据，公开前顺手换成占位符即可。

### P3：技术债（不阻塞发版）

- [ ] **追上游 `v4.29.4`**（不是 master）。已做试合并：26 冲突文件 / 52 冲突块，
  其中 18 个是生成物。**禁止追 master**——`e9879c55f` 把 `astr_main_agent.py` 拆成 14 个模块，
  我们的 241+/244− 全在单文件里，追它等于重做 T8-12。
- [ ] **R11–R15**（可维护性，逐项独立提交）：
  - R11 归因字段 `"a|b|c"` 分隔符编码 → 结构化
  - R12 `control_tags` 硬编码标签词表
  - R13 `event.is_at_or_wake_command = True` 属性赋值式 duck typing
  - R14 `_2`/`_3` 双 schema 长期收敛
  - R15 `plugin_attribution` 扫配置猜 provider 归属
- [ ] **R16 两个大文件拆分**：**明确不做**（上游正在拆 agent，会撞车）

---

## 3. 风险提示（动手前必读）

1. **转公开不可逆**：GitHub 从私有转公开后，历史提交可能已被抓取，改回私有也收不回。
   `docs/maintained/` 有 30+ 份内部文档（含实例路径、插件审计）。**建议走 B 方案**。
2. **`dist/` 不入仓**：改前端后必须 `npm run build`（已内置 `stamp` 步骤），
   再手动同步到实例 `core/data/dist`，否则浏览器跑旧包。
3. **构建戳会因提交而"过期"**：每次 commit 后需重跑 `apply_patches --apply` 刷新，
   否则门禁的 `build stamp` 行会红。这是**设计如此**，不是 bug。
4. **`test_api_frozen.py` 要求新文件先 `git add`**：它用 `git diff baseline` 判断"新增"，
   未入索引的文件看不到。
5. **改 core 必同步台账 SHA-256**，否则 `manifest` 门禁红、部署会漏文件。

---

## 4. 常用命令

```bash
cd /d/asbot_core_for_fork
I="C:/Users/philia093/.astrbot_launcher/instances/83ca721d-26d2-4dd0-9932-ef9299d8829d"

# 一键门禁（-instance 额外查漂移与构建戳）
TMP=/d/pytest_tmp TEMP=/d/pytest_tmp PYTHONDONTWRITEBYTECODE=1 \
  ~/.workbuddy/binaries/python/envs/astrbot-test/Scripts/python.exe \
  maintained/tools/release_gate.py --instance "$I"

# 只跑维护版（跳过 5 分钟的上游套件）
... release_gate.py --instance "$I" --skip-upstream

# 部署（dry-run 默认；--apply 才写，写前自动备份）
... maintained/tools/apply_patches.py --instance "$I" --apply

# 漂移检查
... maintained/tools/check_drift.py --instance "$I" --check-repo

# 前端构建（已内置版本标记）
cd dashboard && npm run build

# 实例重启
PID=$(netstat -ano | grep LISTENING | grep ":6185" | awk '{print $5}' | head -1)
taskkill //PID $PID //F; cd "$I/core" && "$I/venv/Scripts/python.exe" main.py > "$I/run.out.log" 2>&1 &
```

**测试环境铁律**：必须带 `TMP=/d/pytest_tmp TEMP=/d/pytest_tmp`，否则被沙箱判批量删除。

---

## 5. 关键文件索引

| 想知道 | 读 |
|---|---|
| 稳定化方案 + 全部实施记录 | `docs/maintained/stabilization-plan.md` |
| 项目定位（**权威**） | `docs/maintained/proposal.md` §项目定位 |
| 核心差异点（卖点证据） | `docs/maintained/fork-advantages.md` §3 |
| API 契约（可直接公开，0 敏感） | `docs/maintained/api-contract.md` |
| 事件 extras 契约（可直接公开） | `docs/maintained/event-extras-contract.md` |
| 脱敏清单 | `docs/maintained/roadmap.md` §4.2 |
| 项目铁律 | `docs/maintained/project_rules.md` |
| 对外身份 | `README_MAINTAINED.md`、`README.md` |

---

## 6. 下一步建议

**若继续发版**：先推送 23 个提交 → S3（版本号/CHANGELOG/干净实例部署/回滚演练）。

**若先做公开准备**：P1-1（改数字）→ P1-2（重写 README）→ P1-3（入门指南）→ 再谈形态。

**两件事不冲突**：P1 全是文档改动，不影响 S3 发版；建议**先发版（P0）再做公开准备（P1）**，
因为发版会让版本号变化，而 P1 的文档要写版本号。
