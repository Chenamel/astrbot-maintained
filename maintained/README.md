# maintained/ — 本 fork 自有工具区

本目录是 `astrbot-maintained` fork 的自有内容，**不修改任何上游文件**，以避免三方合并冲突。

| 文件 | 用途 |
|---|---|
| `VERSION` | 本 fork 版本号的人类可读副本，与 `astrbot.__version__` 完全一致（当前 `4.28.2+mtn1`），由 `tests/maintained/test_version_marker.py` 校验；不是独立版本来源。 |
| `installed_manifest.json` | 受保护文件的 SHA-256 台账，**只含 core**（`astrbot/**`；当前 **66 条** = 56 个 core + 10 个新增 api 文件），另有 `proactive_must_remain_disabled` 字段。 |
| `tools/check_drift.py` | 漂移检测：比对实例（可选含本仓工作树）与台账，退出码 0/1/2。 |
| `tools/apply_patches.py` | 一键重打：源校验 → 备份 → 写回 → 复核；**默认预演**，`--apply` 才写。 |

> `tools/` 只处理台账内的 core 文件，**不含任何插件信息**（与本仓「只留 core」定位一致）。
> 用法与边界见 [`../docs/maintained/tools.md`](../docs/maintained/tools.md)。

## 校验

台账是**契约**，用以下命令比对（推荐用工具，输出更完整；下面也给出不依赖工具的最小写法）：

```bash
# 推荐：双向校验（实例 + 本仓工作树），无漂移返回 0
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo

# 最小写法（不依赖仓库代码）
python - <<'PY'
import hashlib, json, pathlib
receipt = json.load(open("maintained/installed_manifest.json", encoding="utf-8"))
root = pathlib.Path("<AstrBot core 目录>")
bad = [r for r, h in receipt["files"].items()
       if not (root / r).is_file()
       or hashlib.sha256((root / r).read_bytes()).hexdigest() != h]
print(json.dumps({"compatible_hashes": not bad, "mismatches": bad}, ensure_ascii=False))
raise SystemExit(bool(bad))
PY
```

**注意哈希口径 = 文件磁盘字节**，且仓内文件必须为 LF（`.gitattributes` 保证）。
本仓工作树↔台账的自洽由 `tests/maintained/test_manifest_guard.py` 持续守护。

## 规则

- 任何 core 改动必须同步更新 `installed_manifest.json` 的 SHA-256（六铁律第 5 条）。
- 本目录内容不参与上游合并冲突解决，只随本 fork 演进。
