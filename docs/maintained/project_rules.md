# Project Rules — AstrBot Maintained Fork

> 本文件规定「AI 如何执行」。不与 design.md 冲突，不绑定具体实现细节。

## 项目定位（2026-10-10 用户定调，压倒性约束）

**本 fork 不再是纯个人的私有分支，而是面向社区开源的「轻量级、高灵活度、集成增强版 AstrBot」。**

**核心价值：提供官方主线缺乏的底层扩展 API，提升机制效率，方便插件进行拟人化干预。**

由此推出三条硬性含义（本节优先于其余章节；冲突时以本节为准）：

1. **对外可用性优先** —— 既然要给社区用，`astrbot/api/**` 暴露的接口**必须有清晰文档与注释**；
   **绝不接受任何野路子私有定义裸露在 core / api 面**。落地门槛见 §9。
2. **允许并鼓励"有意偏离官方"** —— 官方为兼容大众而做的妥协，正是本项目要优化的痛点。
   这类偏离必须**显式登记**（`inventory.md` P11 的 β 类即为此），
   且**严禁在上游合并时被官方实现覆盖**（操作要求见 §5）。
3. **对外承诺** —— 上游是 AGPL-3.0，本 fork 与其同源、标注来源、不冒用其名义；
   但**架构主张上本 fork 可以且应当比上游更激进**（在 §2 兼容边界内）。

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

> ⚠️ **合并红线（2026-10-10 定调）**：本 fork 的**架构性优化严禁被上游实现覆盖**。
> 合并前必须对照 `docs/maintained/inventory.md` §4 的 **P11 清单**（尤其 **β 类 hook 完成时序**——
> 那是本项目的核心架构优化，保留现状、坚决不改回上游）。
> 凡冲突落在 P11 登记的文件/语义上，**一律以本 fork 为准**，不做"为了通过上游测试而回退"的处理。

```bash
git fetch upstream --tags --prune
# 临时分支试合
git switch -c tmp/sync-<ref> maintained/v4.28.2
git merge --no-commit --no-ff <upstream ref>
# 冲突只解"我们改过的文件"；骨架文件因零冲突原则不应冲突
# ★ 逐个冲突核对 P11：属 α/β 类偏离的 → 保留本 fork 实现
# 合并后：
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo
ruff check . && pytest tests/maintained
# ★ 合并后必须复核：P11 的 α/β 偏离是否仍在（语义级，不只看测试颜色）
```

## 6. 提交前自检命令

```bash
cd /d/asbot_core_for_fork

# 身份与 remote
git remote -v                    # upstream 禁推 / origin 为 SSH
git rev-parse --abbrev-ref HEAD  # maintained/v4.28.2

# 台账：默认双向校验（实例 + 仓内），无漂移才返回 0
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo

# 若报出漂移：先预演再执行（工具只碰台账内文件，写前自动备份）
python maintained/tools/apply_patches.py --instance "<实例目录>"
python maintained/tools/apply_patches.py --instance "<实例目录>" --apply
```

# 换行
git config --get core.autocrlf          # false
git ls-files --eol | awk '$1=="crlf"' | wc -l   # 0

# 私有代码残留（三条必须全空）
grep -rIn "astrbot_plugin_astrbot_enhance_mode" --exclude-dir=.git . | head
grep -rIn "astrbot_plugin_content_safety_guard" --exclude-dir=.git . | head
grep -rIn "Axi404" --exclude-dir=.git . | head
git ls-files | grep -i "data/plugins" | head        # 空
git ls-files | grep -iE "(^|/)configs/config\.yaml$|(^|/)\.env$" | head   # 空
#   ↑ 必须锚定路径：早先的 `config\.yaml` 会误命中 .pre-commit-config.yaml / openspec/config.yaml

# 台账（只应含 core 条目）
python -c "import json;d=json.load(open('maintained/installed_manifest.json',encoding='utf-8'));f=d['files'];\
print(len(f), all(k.startswith('astrbot/') for k in f))"   # 期望：31 True

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
  `GIT_SSH_COMMAND="ssh -i <本机ssh私钥路径> -o IdentitiesOnly=yes -F /dev/null"`
- 后台任务不继承沙箱提权，**涉及 SSH 密钥的 git 操作必须前台执行**。
- **测试**用专用测试 venv（Python 3.12.13，含运行依赖 + pytest + pytest-asyncio）：
  `<托管binaries>/python/envs/astrbot-test/Scripts/python.exe -m pytest tests/maintained -q`
  备用方案与理由见 `tests/maintained/README.md`。**禁止**往 AstrBot 实例 venv 安装任何包。
- `ruff` 用托管工具 venv（`<托管binaries>/python/envs/default`），版本 `0.15.22`。
- **写 JSON / 台账 / 任何要求字节精确的文件，用 `Path.write_bytes(...)`**：
  Windows 上 `write_text` 会把 `\n` 翻译成 `\r\n`，破坏台账哈希口径。
  改完换行敏感文件后复核：`git ls-files --eol | awk -F'\t' '{split($1,a," "); if (a[2]=="w/crlf") print $2}'`。
- **台账哈希口径 = 文件磁盘字节**（非 LF 归一化）。`.gitattributes` 会按 `eol=lf` 归一化，
  故**入仓文件必须是 LF**，否则新克隆后哈希对不上、漂移检测永久误报。

## 9. api 面文档门槛（对外可用的前提）

> 依据「项目定位」第 1 条：既然面向社区开源，公开面必须**可读、可依赖、可降级**。

**对 `astrbot/api/**` 下本 fork 新增的每个模块，缺一不可：**

| 要求 | 判定方式 |
|---|---|
| 模块级 docstring：说明**用途**、**公开符号清单**、**降级行为** | `ast.get_docstring(tree)` 非空 |
| 每个导出符号有 docstring：含参数含义 + 返回值/降级语义 | 逐符号检查 |
| 每个公开常量有 `#:` 注释：说明**取值**与**语义** | 逐常量检查 |
| 显式 `__all__`，且与 `docs/maintained/api-contract.md` **一一对应** | `test_api_surface.py` 的 `EXPECTED_ALL` |
| 未导出但公开名的常量 → **违规** | 见下方"禁止项" |

**禁止项（"野路子私有定义"）：**

- **禁止**模块里出现「名字不带 `_` 前缀、却既不在 `__all__`、也不在契约、也没有测试」的定义。
  两条出路：① 纳入 `__all__` + 契约 + 测试；② 加 `_` 前缀降为模块私有。
- **禁止**把 core 内部符号（尤其补丁私有符号如 `direct_turns.*`、`_direct_turn_*`）
  以原名直接裸露在公开面；必须经 `_bridge.resolve` 转发，并提供缺失时的降级语义。
- **禁止**新增能力绕过 `astrbot/api/**` 直接给插件用（六铁律第 1 条）。

**违规后果**：不得登记进 `maintained/installed_manifest.json`，即**不得部署到实例**。

**已登记待修**：`astrbot/api/permissions/__init__.py` 的 `EXECUTION_POLICY_UNAVAILABLE`
（公开名、不在 `__all__`、不在契约）—— 按本条降为 `_EXECUTION_POLICY_UNAVAILABLE`，
并在 `api-contract.md` §3.4 以文字说明该拒绝原因的语义。
