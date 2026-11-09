# 维护工具链（阶段 6）

> 回答一个问题：启动器又把 core 覆盖了怎么办？ 答案是两条命令。

## 0. 背景

10-08 的事故是「启动器更新核心 → 26 个补丁被官方覆盖 → 插件 import 不到私有符号 →
整体加载失败」。事后排查全靠人工比对，耗时且有遗漏风险（本次审计才发现补丁压根没进仓）。

阶段 6 把这两个动作固化成工具：

| 工具 | 作用 | 何时用 |
|---|---|---|
| `maintained/tools/check_drift.py` | 检测实例 core 是否与台账（=维护版真相源）不一致 | 机器人异常时、启动器更新后、定期巡检 |
| `maintained/tools/apply_patches.py` | 修复：把仓内维护版 core 打回实例（带备份与校验） | check_drift 报出漂移后 |
| `maintained/tools/hook_timing_probe.py` | 取证：记录并校验 agent 完成钩子相对最终回复的时序 | T8-12 每步拆分前后（β 红线） |

## 1. 共同约定

- 真相源：`maintained/installed_manifest.json`（登记本 fork 改动过的 `astrbot/**` 文件，条数以该文件为准）。
  - 判定口径：凡是本 fork 改动过的 `astrbot/**` 文件都必须登记，否则 `apply_patches` 不会部署它；
    若该文件又被别的已登记文件 import，就会在实例侧 `ImportError`（曾由此导致启动失败）。
  - 双端校验：一端是实例的工作树，另一端是 fork 仓的工作树。
- 哈希口径：文件磁盘字节的 SHA-256。仓内文件全部为 LF。
- 目标根：`--instance <实例目录>`，工具自动定位其下的 `core/`。
- 只碰台账内的文件：工具不会读写台账之外的任何文件（不动 `data/`、不动配置、不动插件）。
- 不含任何插件信息：与本仓「只留 core」的定位一致，工具里没有插件名。

## 2. `check_drift.py`

```bash
# 人读输出
python maintained/tools/check_drift.py --instance "<实例目录>"

# 机器读（JSON）
python maintained/tools/check_drift.py --instance "<实例目录>" --json

# 同时校验「仓内工作树」是否也与台账一致（默认只校验实例）
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo
```

输出：每条文件的状态（`ok` / `mismatch` / `missing`），以及计数与结论。

退出码：`0` 无漂移；`1` 有漂移；`2` 用法/环境错误（如实例路径不存在、台账读不到）。
便于直接接进自动化（例如让机器人在启动后自检并告警）。

## 3. `apply_patches.py`

```bash
# 预演（默认行为，不写任何文件）
python maintained/tools/apply_patches.py --instance "<实例目录>"

# 真正执行（写文件 + 先备份）
python maintained/tools/apply_patches.py --instance "<实例目录>" --apply
```

行为：

1. 读台账，逐个核对源文件（fork 仓工作树）哈希与台账一致 → 不一致则中止（源损坏，宁可不做）。
2. 计算计划：`create`（实例缺失）/ `update`（内容不符）/ `skip`（已一致）。
3. `--apply` 时先备份到 `<实例>/optimization_backups/<时间戳>_CST_apply_patches/`
   （只备份将被覆盖的文件 + 一份记录操作前状态的 `manifest.json`）。
4. 逐文件复制，随后立即复核台账，输出最终一致率。
5. 绝不动台账之外的文件；绝不删除任何东西。

退出码：`0` 成功（或无变化）；`1` 复核后仍有不符；`2` 用法/源校验失败。

**注意**：写完 core 源码后需重启 AstrBot 才生效（工具不做重启，避免突然中断正在跑的任务）。

## 4. `hook_timing_probe.py`

T8-12 要拆分四个过大的 core 文件，而 **β（agent 完成钩子的时序）必须逐点保真**。
该探针把「钩子相对于最终回复的位置」记录下来，供每一步拆分后机械比对。

```bash
# 落盘基线（按 commit 命名）
python maintained/tools/hook_timing_probe.py --quiet --dump maintained/baselines/hook_timing/<shortsha>.json

# 与基线比对
python maintained/tools/hook_timing_probe.py --quiet --compare maintained/baselines/hook_timing/<shortsha>.json
```

**5 个 case**（括号为落盘时的行号）：`image_unavailable`(984) / `no_tool_call`(1100) /
`requery_enhanced`(1142) / `requery_legacy`(1166) / `tool_failure_final`(1340)。

**不变量（只比相对关系，不比绝对行号）**：

- `enhanced` ⇒ `hook_index < first_final_yield_index`
- `legacy` ⇒ `hook_index > first_final_yield_index`
- 984 / 1100 / 1340 **没有** `legacy_timing` 分支 ⇒ 两种模式下结果必须完全相同（`mode_symmetry`）

**结构守卫**：每次运行都符号化扫描 runner，断言 `await self._complete_with_assistant_response(`
恰好 **5 处**，其中 enhanced 分支 1 处、legacy 分支 1 处、无条件 3 处，**不依赖行号**，
所以拆分后行号漂移不会误报，但少一处/多一处立刻判红。

**比对范围**：只比 `events` / `summary` / `mode_symmetry`。`repo_commit` 与 `case.call_site`
是信息字段，本就会随改动移动，不参与比对。

**退出码**：`0` 一致；`1` 有 case / 不变量 / 结构守卫失败；`2` 用法或环境错误。
`--quiet` 只压制 runner 自身的日志（它会打 traceback），不影响判定。

## 5. 典型处置流程

```bash
# 1. 发现机器人异常 / 启动器更新过核心
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo

# 2. 若报出漂移：先预演，看要改哪些文件
python maintained/tools/apply_patches.py --instance "<实例目录>"

# 3. 确认无误后执行
python maintained/tools/apply_patches.py --instance "<实例目录>" --apply

# 4. 重启 AstrBot，再用 check_drift 复查
```

## 6. 明确不做

- **不拦启动器**（做不到：拦不住进程外的文件覆盖）。本工具链的定位是**事后快速检测 + 一键恢复**，
  把 MTTR 从"人工排查半小时"降到"两条命令"。
- 不自动重启机器人、不改配置、不动插件、不碰 `data/`。
- 不做「上游版本升级」，那走三方合并，与本工具无关。

## 7. `sync_audit.py`（升级覆盖审计）

与 `check_drift.py` 不同：后者只比台账 68 条，前者以**两个上游基线之间的全量变更面**为参照，
查签名漂移、上游新增模块/依赖、前端悬空 import、i18n 注册、API 导出零删减，
以及实例侧的全量 core / venv / 面板 / 戳记 / 配置键。只读、纯标准库、可输出 JSON。

```bash
PYTHONPATH=maintained python -m tools.sync_audit
PYTHONPATH=maintained python -m tools.sync_audit --instance "<实例目录>"
PYTHONPATH=maintained python -m tools.sync_audit --json
```

已在 `maintained-ci.yml` 的 `static-checks` job 接入静态层。完整判据、分级与误报豁免见
`docs/maintained/upstream-sync-audit.md`。

## 8. 测试

`tests/maintained/test_tools_check_drift.py` / `test_tools_apply_patches.py` /
`test_tools_hook_timing_probe.py` / `test_sync_audit.py`：
用 `tmp_path` 造出「假仓 + 假实例」，覆盖无漂移 / 内容不符 / 文件缺失 / 源损坏中止 /
预演不写文件 / `--apply` 备份与写回 / 写回后复核，以及审计对四类已知事故的检出与误报豁免。
