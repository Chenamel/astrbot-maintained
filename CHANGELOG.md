# Changelog — AstrBot Maintained Fork

本文件记录**本 fork 相对上游**的变更。上游自身的变更记录见 `changelogs/`（未改动）。

格式参照 Keep a Changelog，版本标签形如 `maintained/v4.28.2-rN`。

## 基线

- **阶段 1 基线**：`3c7adafa1397e182d60b1016bf88759265113c8a`（上游 tag `v4.28.2`）。
- 本 fork 从此提交起家，主干分支 `maintained/v4.28.2`，锚点标签 `baseline/v4.28.2`。

## [未发布]

### 新增

- 仓库骨架：remote（`upstream` 只读 / `origin` 指向本 fork）、主干分支与锚点标签。
- 规范文档 `docs/maintained/`：`proposal.md`、`design.md`、`tasks.md`、`project_rules.md`。
  按 sdd 规范跳过 `docs/layouts/`（本项目无 UI）。
- 合规文件 `NOTICE`（AGPL §13）与 `README_MAINTAINED.md`。
- `.gitattributes`（LF 归一化）与 `.gitignore` 追加段（私有代码黑名单）。
- `maintained/`：`installed_manifest.json`（65 条 SHA-256 台账，自归档仓原样迁入）、
  `tools/update_local.py`（离线 `--check` 校验器）、`VERSION`。

### 未做

- 未修改任何 core 代码；未恢复任何补丁（止血在阶段 4）。
- 未引入第三方插件源码（该插件无许可证，只能进私有仓）。
