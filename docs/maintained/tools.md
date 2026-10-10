# 维护工具链（阶段 6）

> 回答一个问题：**启动器又把 core 覆盖了怎么办？** 答案是两条命令。

## 0. 背景

10-08 的事故是「启动器更新核心 → 26 个补丁被官方覆盖 → 插件 import 不到私有符号 →
整体加载失败」。事后排查全靠人工比对，耗时且有遗漏风险（本次审计才发现补丁压根没进仓）。

阶段 6 把这两个动作固化成工具：

| 工具 | 作用 | 何时用 |
|---|---|---|
| `maintained/tools/check_drift.py` | **检测**实例 core 是否与台账（=维护版真相源）不一致 | 机器人异常时、启动器更新后、定期巡检 |
| `maintained/tools/apply_patches.py` | **修复**：把仓内维护版 core 打回实例（带备份与校验） | check_drift 报出漂移后 |

## 1. 共同约定

- **真相源**：`maintained/installed_manifest.json`（**33 条**：24 个 core 文件 + 9 个 `astrbot/api` 文件）
  - 判定口径：**凡是本 fork 改动过的 `astrbot/**` 文件都必须登记**，否则 `apply_patches` 不会部署它；
    若该文件又被别的已登记文件 import，就会在实例侧 `ImportError`（曾由此导致启动失败）。
  + fork 仓的工作树。
- **哈希口径**：文件**磁盘字节**的 SHA-256。仓内文件全部为 LF（见 `project_rules.md` §8）。
- **目标根**：`--instance <实例目录>`，工具自动定位其下的 `core/`。
- **只碰台账内的文件**：工具不会读写台账之外的任何文件（不动 `data/`、不动配置、不动插件）。
- **不含任何插件信息**：与本仓「只留 core」的定位一致，工具里没有插件名。

## 2. `check_drift.py`

```bash
# 人读输出
python maintained/tools/check_drift.py --instance "<实例目录>"

# 机器读（JSON）
python maintained/tools/check_drift.py --instance "<实例目录>" --json

# 同时校验「仓内工作树」是否也与台账一致（默认只校验实例）
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo
```

**输出**：每条文件的状态（`ok` / `mismatch` / `missing`），以及计数与结论。

**退出码**：`0` 无漂移；`1` 有漂移；`2` 用法/环境错误（如实例路径不存在、台账读不到）。
便于直接接进自动化（例如让机器人在启动后自检并告警）。

## 3. `apply_patches.py`

```bash
# 预演（默认行为，不写任何文件）
python maintained/tools/apply_patches.py --instance "<实例目录>"

# 真正执行（写文件 + 先备份）
python maintained/tools/apply_patches.py --instance "<实例目录>" --apply
```

**行为**：

1. 读台账，逐个核对**源文件**（fork 仓工作树）哈希与台账一致 → 不一致则**中止**（源损坏，宁可不做）。
2. 计算计划：`create`（实例缺失）/ `update`（内容不符）/ `skip`（已一致）。
3. `--apply` 时先备份到 `<实例>/optimization_backups/<时间戳>_CST_apply_patches/`
   （只备份将被覆盖的文件 + 一份记录操作前状态的 `manifest.json`）。
4. 逐文件复制，随后**立即复核**台账，输出最终一致率。
5. **绝不动**台账之外的文件；**绝不**删除任何东西。

**退出码**：`0` 成功（或无变化）；`1` 复核后仍有不符；`2` 用法/源校验失败。

**注意**：写完 core 源码后需**重启 AstrBot** 才生效（工具不做重启，避免突然中断正在跑的任务）。

## 4. 典型处置流程

```bash
# 1. 发现机器人异常 / 启动器更新过核心
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo

# 2. 若报出漂移：先预演，看要改哪些文件
python maintained/tools/apply_patches.py --instance "<实例目录>"

# 3. 确认无误后执行
python maintained/tools/apply_patches.py --instance "<实例目录>" --apply

# 4. 重启 AstrBot，再用 check_drift 复查
```

## 5. 明确不做

- **不拦启动器**（做不到：拦不住进程外的文件覆盖）。本工具链的定位是**事后快速检测 + 一键恢复**，
  把 MTTR 从"人工排查半小时"降到"两条命令"。
- 不自动重启机器人、不改配置、不动插件、不碰 `data/`。
- 不做「上游版本升级」——那走三方合并（`project_rules.md` §5），与本工具无关。

## 6. 测试

`tests/maintained/test_tools_check_drift.py` / `test_tools_apply_patches.py`：
用 `tmp_path` 造出「假仓 + 假实例」，覆盖无漂移 / 内容不符 / 文件缺失 / 源损坏中止 /
预演不写文件 / `--apply` 备份与写回 / 写回后复核 等分支。
