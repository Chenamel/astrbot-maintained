# Project Rules — AstrBot Maintained Fork

> 本文件规定「AI 如何执行」。不与 design.md 冲突，不绑定具体实现细节。

## 0. 仓库事实

```
upstream : https://github.com/AstrBotDevs/AstrBot   (remote 名 upstream，禁 push)
origin   : git@github.com:Chenamel/astrbot-maintained.git  (SSH)
baseline : tag v4.28.2 = 3c7adafa1397e182d60b1016bf88759265113c8a
           锚点 tag: baseline/v4.28.2
主分支   : maintained/v4.28.2（默认分支；升基线不改名，只打新 tag）
发布 tag : maintained/v4.28.2-rN
私有仓   : Chenamel/astrbot-extras（永远私有，无许可证）
归档仓   : <INST>/maintenance_repos/astrbot_local（只读快照，不加 remote、不 push）
```

4.28.2 真实布局为 `astrbot/core/...`（非旧的 `astrbot/...`）。

## 1. 六铁律（违反即打回）

1. **新增能力只落 `astrbot/api/**`**；外部（插件）只允许 `import astrbot.api.*`。
2. **先文档后代码**：改动前先更新 `docs/maintained/` 对应文档，再动代码。
3. **一改动一提交**：一次逻辑改动 = 一次 commit，语义化前缀 `fix / feat / docs / chore / test / refactor`。
4. **无测试不进阶段 4+**：阶段 4 起每个改动必须附 `tests/maintained/` 下的测试。
5. **改 core 同步更新 `maintained/installed_manifest.json` 的 SHA-256**，并按 `maintained/README.md` 的比对脚本复核。
6. **不动主动回复开关**：`proactive_must_remain_disabled` 恒为 true，任何代码路径不得打开。

## 2. 兼容边界三规则

- **冻结**：`astrbot/api/**` 现存全部符号；以及 core 中被插件事实依赖的 5 个路径
  （`TextPart` / `EmbeddingProvider` / `get_astrbot_data_path` / `download_image_by_url` / `extract_quoted_message_images`）。
- **加法**：新模块 / 新钩子 / 新可选参数 —— **默认值必须保持旧行为**。
- **shim 例外**：确需重命名 core 内部私有模块时，必须 shim + `DeprecationWarning` + 测试 + **单独提交**并说明理由。

## 3. 零冲突原则

- 本 fork 自有内容一律走**新增路径**：
  `NOTICE` / `CHANGELOG.md` / `README_MAINTAINED.md` / `maintained/**` / `docs/maintained/**` / `tests/maintained/**`。
- **禁止修改上游既有文件**，除非属于已登记的 core 补丁。
- **唯一例外：`README.md`**（GitHub 首页渲染入口，代表本 fork 身份）。
  已替换为 fork 说明，并在 `.gitattributes` 声明 `README.md merge=ours`、
  本仓配置 `merge.ours.driver`，上游对 README 的改动**永不覆盖本 fork 版本**；
  上游原文可从 `upstream/master` 或 git 历史随时取回。
- **禁止** `git add --renormalize .`；**禁止**批量 reformat。
- **不删上游 md/docs**：全部 md 合计约 2.4MB 且已永久存在于 git 历史，
  删工作区文件不节省空间，只会制造 delete/modify 合并冲突。

## 4. 隔离红线

- 增强插件 `astrbot_plugin_astrbot_enhance_mode`、内容安全插件的**源码与文件清单**，**一律不得出现在 `astrbot-maintained`**，只能进 `astrbot-extras`。
- `maintained/installed_manifest.json` **只登记 core（`astrbot/**`）**；`data/plugins/**` 与 `dashboard/**` 条目留在归档仓与私有仓。
- `data/`、`configs/config.yaml`、`.env`、`*.log`、`venv` 永不入仓。
- 提交前必跑 §6 自检。

## 5. 上游同步流程

```bash
git fetch upstream --tags --prune
# 临时分支试合
git switch -c tmp/sync-<ref> maintained/v4.28.2
git merge --no-commit --no-ff <upstream ref>
# 冲突只解"我们改过的文件"；骨架文件因零冲突原则不应冲突
# 合并后：
python -c "见 maintained/README.md 的台账比对脚本"
ruff check . && pytest tests/maintained
```

## 6. 提交前自检命令

```bash
cd /d/asbot_core_for_fork

# 身份与 remote
git remote -v                    # upstream 禁推 / origin 为 SSH
git rev-parse --abbrev-ref HEAD  # maintained/v4.28.2

# 换行
git config --get core.autocrlf          # false
git ls-files --eol | awk '$1=="crlf"' | wc -l   # 0

# 私有代码残留（三条必须全空）
grep -rIn "astrbot_plugin_astrbot_enhance_mode" --exclude-dir=.git . | head
grep -rIn "astrbot_plugin_content_safety_guard" --exclude-dir=.git . | head
grep -rIn "Axi404" --exclude-dir=.git . | head
git ls-files | grep -i "data/plugins" | head        # 空
git ls-files | grep -iE "config\.yaml|\.env$" | head # 空

# 台账（只应含 core 条目）
python -c "import json;d=json.load(open('maintained/installed_manifest.json',encoding='utf-8'));f=d['files'];\
print(len(f), all(k.startswith('astrbot/') for k in f))"   # 期望：22 True

# 归档仓只读性
git -C "<INST>/maintenance_repos/astrbot_local" status --porcelain | wc -l   # 0

# 静态检查（托管 venv 装 ruff==0.15.22，禁止装进实例 venv）
ruff check .
```

## 7. 阶段门禁

每阶段结束**必须停下**，向用户汇报 **≤10 行**（产出 + 遗留问题），等明确确认后才可进入下一阶段。
**禁止连续推进多个阶段。**

## 8. 环境注意事项

- 全局已设 `core.autocrlf=false`、`core.eol=lf`、`core.longpaths=true`，**不要改回**。
- GitHub 操作：本机无 `gh` CLI；GitHub MCP 连接器**无 repo 写权限**（建仓需 PAT 或浏览器手动建）。
- 大流量 git 操作走 **SSH**（HTTPS 会被代理以 `CONNECT tunnel failed 502` 掐断）；SSH 需显式传密钥：
  `GIT_SSH_COMMAND="ssh -i C:/Users/philia093/.ssh/id_ed25519_workbuddy -o IdentitiesOnly=yes -F /dev/null"`
- 后台任务不继承沙箱提权，**涉及 SSH 密钥的 git 操作必须前台执行**。
