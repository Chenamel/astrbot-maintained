# 维护工具链手册

> 启动器升级核心或外部操作覆盖本地文件后，使用以下工具完成漂移检测、补丁重放、钩子时序校验与升级覆盖审计。

## 0. 工具一览

| 工具脚本 | 核心用途 | 适用场景 |
|---|---|---|
| `maintained/tools/check_drift.py` | 校验运行实例及仓库工作树的 `astrbot/**` 文件是否与 SHA-256 台账一致 | 日常巡检、启动器更新后、排查能力异常时 |
| `maintained/tools/apply_patches.py` | 将仓库内的维护版 core 文件同步到运行实例（自动备份被覆盖文件并复核） | `check_drift.py` 检出文件缺失或哈希不匹配后 |
| `maintained/tools/hook_timing_probe.py` | 记录并校验 agent 完成钩子相对于最终回复产出的时序关系 | 修改或重构 `tool_loop_agent_runner.py` 前后 |
| `maintained/tools/sync_audit.py` | 对比两个上游 `baseline/*` 标签之间的全量变更面，核查仓库与实例是否完整吸收 | 每次跟进上游正式版本升级后 |

## 1. 通用约定

- **单一台账真相源**：`maintained/installed_manifest.json` 登记本分支修改或新增的全部 `astrbot/**` 文件路径及磁盘字节 SHA-256（仓库文件统一为 LF 换行符）。凡是修改过的 `astrbot/**` 文件均须登记入台账，否则 `apply_patches.py` 不会将其部署到实例。
- **实例路径解析**：通过 `--instance "<实例目录>"` 传入实例根目录，工具会自动定位其下的 `core/` 目录。
- **操作边界**：工具仅读写台账内登记的 `astrbot/**` 文件（及备份目录 `<实例目录>/optimization_backups/`），绝不修改 `data/` 运行时数据、配置文件或任何插件目录。

## 2. `check_drift.py`（漂移检测）

```bash
# 人类可读报告（检查运行实例）
python maintained/tools/check_drift.py --instance "<实例目录>"

# 机器可读 JSON 输出
python maintained/tools/check_drift.py --instance "<实例目录>" --json

# 同时校验仓库工作树与运行实例双端一致性
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo
```

输出逐个受保护文件的状态（`ok` / `mismatch` / `missing`）及汇总统计。
退出码：`0` 表示完全一致；`1` 表示存在漂移；`2` 表示参数错误或台账不可读。

## 3. `apply_patches.py`（补丁重放与恢复）

```bash
# 只读预演（默认行为，不修改任何文件）
python maintained/tools/apply_patches.py --instance "<实例目录>"

# 执行写入（先备份目标文件，再复制并复核哈希）
python maintained/tools/apply_patches.py --instance "<实例目录>" --apply
```

执行流程：
1. 读取 `maintained/installed_manifest.json`，先校验当前仓库工作树中的源文件哈希与台账是否完全一致；若源文件不一致则立即中止（退出码 `2`）。
2. 计算实例侧变更计划：`create`（实例缺失）、`update`（哈希不符）、`skip`（已一致）。
3. 传入 `--apply` 时，先将被覆盖的实例文件备份至 `<实例目录>/optimization_backups/<时间戳>_CST_apply_patches/`（附带记录操作前状态的 `manifest.json`）。
4. 复制文件并立即重新计算 SHA-256 复核，输出最终一致率。

退出码：`0` 表示同步成功（或无需变更）；`1` 表示复核仍存在不一致；`2` 表示用法错误或源文件校验失败。写入完成后需重启 AstrBot 实例使新代码生效。

## 4. `hook_timing_probe.py`（完成钩子时序探针）

重构或拆分 runner 相关文件时，agent 完成钩子（`_complete_with_assistant_response`）相对于最终回复 yield 的触发时序必须保持不变。该探针用于记录并机械比对 5 个标准分支的时序关系。

```bash
# 导出当前基线快照
python maintained/tools/hook_timing_probe.py --quiet --dump maintained/baselines/hook_timing/<shortsha>.json

# 与基线快照机械比对
python maintained/tools/hook_timing_probe.py --quiet --compare maintained/baselines/hook_timing/<shortsha>.json
```

- **覆盖的 5 个标准分支**：`image_unavailable`、`no_tool_call`、`requery_enhanced`、`requery_legacy`、`tool_failure_final`。
- **核心时序不变量（仅比对相对事件顺序，不依赖源码绝对行号）**：
  - `enhanced` 分支：`hook_index < first_final_yield_index`（钩子先于回复触发）
  - `legacy` 分支：`hook_index > first_final_yield_index`（回复先于钩子发出）
  - 无模式分支区分的 3 个路径（`image_unavailable`、`no_tool_call`、`tool_failure_final`）：两种模式下产出事件序列完全一致（`mode_symmetry`）。
- **AST 结构守卫**：每次运行自动扫描 `tool_loop_agent_runner.py`，断言 `await self._complete_with_assistant_response(` 调用点恰好为 **5 处**（`enhanced` 分支 1 处、`legacy` 分支 1 处、无条件调用 3 处）。
- **比对字段**：仅比对 `events`、`summary` 与 `mode_symmetry`；忽略随提交变动的 `repo_commit` 与行号字段 `case.call_site`。
- **退出码**：`0` 一致；`1` 时序不变量或结构守卫失败；`2` 参数或环境错误。

## 5. 标准恢复流程

```bash
# 1. 检查实例与仓库是否存在漂移
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo

# 2. 预演修复计划
python maintained/tools/apply_patches.py --instance "<实例目录>"

# 3. 执行备份与同步
python maintained/tools/apply_patches.py --instance "<实例目录>" --apply

# 4. 重启 AstrBot 实例后复查
python maintained/tools/check_drift.py --instance "<实例目录>"
```

## 6. `sync_audit.py`（升级覆盖审计）

`check_drift.py` 仅校验台账内登记的文件，而 `sync_audit.py` 以两个上游 `baseline/*` 标签之间的全量变更面为参照，检查函数签名变更、上游新增模块与依赖、前端本地导入、四语言 i18n 注册、`astrbot/api/all.py` 导出完整性及实例侧全量文件同步情况：

```bash
PYTHONPATH=maintained python -m tools.sync_audit
PYTHONPATH=maintained python -m tools.sync_audit --instance "<实例目录>"
PYTHONPATH=maintained python -m tools.sync_audit --json
```

完整检查项定义（S1–S8、I1–I5）与误报豁免规则见 [`upstream-sync-audit.md`](./upstream-sync-audit.md)。

## 7. 对应测试套件

`tests/maintained/test_tools_check_drift.py`、`test_tools_apply_patches.py`、`test_tools_hook_timing_probe.py` 与 `test_sync_audit.py` 使用临时目录构造模拟仓库与实例，覆盖正常校验、内容漂移、文件缺失、源损坏中止、只读预演、备份写回及时序探针断言。

## 9. L2 盲评

`maintained/tools/l2_blind_eval.py` 倒读 `shadow_log.jsonl` 尾部，按四条红线打标、
生成打乱编码的盲评表与单独保存的揭盲映射，再读入评分生成汇总表。纯标准库、
离线、不写实例、不发送消息；红线的正则与阈值写在脚本顶部常量里。

```bash
python maintained/tools/l2_blind_eval.py --selftest
python maintained/tools/l2_blind_eval.py --mode flag --log "<实例目录>/core/data/plugins/<插件目录>/shadow_log.jsonl"
```

机器人称呼用环境变量 `L2_BOT_NICKNAMES`（逗号分隔）传入，只用于清洗盲样里的称呼；
不设置时只剥离通用前缀。配套测试见 `tests/maintained/test_l2_blind_eval.py`。
