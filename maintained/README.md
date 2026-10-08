# maintained/ — 本 fork 自有工具区

本目录是 `astrbot-maintained` fork 的自有内容，**不修改任何上游文件**，以避免三方合并冲突。

| 文件 | 用途 |
|---|---|
| `VERSION` | 本 fork 的维护版本号（形如 `4.28.2.m1`）。上游 `pyproject.toml` 与 `astrbot.__version__` 保持 `4.28.2` 不变。 |
| `installed_manifest.json` | 受保护文件的 SHA-256 台账，**只含 core（`astrbot/**`，22 条）**，另有 `proactive_must_remain_disabled` 字段。 |
## 校验

台账是**契约**，可用任意方式比对。公开仓不附带实例运维脚本（那些脚本涉及私有插件，
不属于 core 项目本体），它们保留在维护归档仓与私有仓。

```bash
# 校验实例中受保护 core 文件是否与台账一致
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

阶段 6 会按类官方范式重写 `check_drift` / `apply_patches` 工具链。

## 规则

- 任何 core 改动必须同步更新 `installed_manifest.json` 的 SHA-256（六铁律第 5 条）。
- 本目录内容不参与上游合并冲突解决，只随本 fork 演进。
