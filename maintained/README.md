# maintained/ — 本 fork 自有工具区

本目录是 `astrbot-maintained` fork 的自有内容，**不修改任何上游文件**，以避免三方合并冲突。

| 文件 | 用途 |
|---|---|
| `VERSION` | 本 fork 的维护版本号（形如 `4.28.2.m1`）。上游 `pyproject.toml` 与 `astrbot.__version__` 保持 `4.28.2` 不变。 |
| `installed_manifest.json` | 受保护文件的 SHA-256 台账，**只含 core（`astrbot/**`，22 条）**，另有 `proactive_must_remain_disabled` 字段。 |
| `tools/update_local.py` | 离线校验器。`--check` 比对目标实例的台账哈希；`--ref` 做三方合并预演（**不触碰运行中的文件**）。 |

## 用法

```bash
# 校验实例中受保护文件是否与台账一致（不一致则非零退出）
python maintained/tools/update_local.py core --check --instance "<实例路径>"

# 预演上游三方合并
python maintained/tools/update_local.py core --ref v4.28.2 --instance "<实例路径>"
```

## 规则

- 任何 core 改动必须同步更新 `installed_manifest.json` 的 SHA-256（六铁律第 5 条）。
- 本目录内容不参与上游合并冲突解决，只随本 fork 演进。
