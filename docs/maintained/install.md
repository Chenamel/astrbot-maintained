# 安装与运行

本页说明如何安装与运行 AstrBot 维护分支。本分支持续跟随上游正式发布版本更新，配置文件格式与上游兼容，已安装的上游插件无需修改即可继续使用。与官方原版的功能差异见 [`fork-advantages.md`](./fork-advantages.md)。

> 本仓库只发布 core 本体，不包含任何插件。插件需另行获取与安装，不在本仓库的打包与发布范围内。本文仅说明 core 的安装与校验方式。
>
> 面板使用、平台适配器配置、模型接入、插件开发等通用内容请查阅官方文档（仓库内副本 `docs/zh/`，或 <https://docs.astrbot.app>）。

## 1. 准备

- Python 3.12 或更高（`pyproject.toml` 中 `requires-python = ">=3.12"`）
- `uv`（通过 `uv sync` 管理依赖）
- git

支持 Windows、macOS 与 Linux。

## 2. 三种安装方式

### 方式 A：源码运行

克隆本仓库并进入仓库根目录后执行：

```bash
uv sync
uv run main.py
```

### 方式 B：wheel 安装

从 [Releases](https://github.com/Chenamel/astrbot-maintained/releases) 下载对应版本的 `.whl` 文件（版本号与 `maintained/VERSION` 一致，形如 `4.29.4+mtn1`）后执行：

```bash
pip uninstall -y astrbot        # 若装过官方包需先卸载，避免同导入名文件互相覆盖
pip install "./astrbot_maintained-<version>-py3-none-any.whl"
astrbot run
```

> 文件名含 `+` 号，部分 shell（尤其是 PowerShell）会将其视为特殊字符，请使用 `./文件名` 或为文件名加上引号。
>
> **尚未发布到 PyPI。** 本分支分发包名为 `astrbot-maintained`，但 **Python 导入名仍为 `astrbot`**，以保证上游插件 `import astrbot` 无需改动。同一 Python 环境内只能保留其中一份，安装前请先卸载官方包。
>
> ⚠️ **自行构建 wheel 时须显式打包 WebUI**。Releases 发布的 wheel 已包含 `astrbot/dashboard/dist/` 前端产物；本地自行构建时必须传入环境变量：
>
> ```bash
> ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
> ```
>
> 未设置该变量构建出的 wheel 不含面板静态文件，启动后访问 6185 端口将无法打开界面。构建前置依赖为 Node.js 与 pnpm 10（详见 [`dashboard-build.md`](./dashboard-build.md)）。可用以下命令校验 wheel 内是否包含面板文件（完整构建应输出约 272）：
>
> ```bash
> python -c "import zipfile,glob;z=zipfile.ZipFile(glob.glob('*.whl')[0]);print(sum('dashboard/dist/' in n for n in z.namelist()))"
> ```

### 方式 C：容器部署

仓库根目录的 `compose.yml` 引用的是上游官方镜像 `soulter/astrbot:latest`，直接执行 `docker compose up` 启动的是官方原版。

如需容器部署，请基于仓库根目录的 `Dockerfile` 自行构建镜像：

```bash
docker build -t astrbot-maintained:local .
docker run -d --name astrbot -p 6185:6185 \
  -v /path/to/data:/AstrBot/data astrbot-maintained:local
```

本仓库未发布公共容器镜像 tag。

## 3. 启动后

- WebUI 默认地址为 `http://localhost:6185`，平台适配器、模型与插件开关均在**面板 → 配置页**设置。
- 配置、插件、日志等运行时数据存放在仓库下的 `data/` 目录，该目录不纳入版本控制。
- 首次启动按面板引导完成初始化即可；配置文件格式与当前上游正式版兼容。
- 启动日志的艺术字下方会打印一行 `AstrBot Maintained Fork <版本号>`（当前值见 `maintained/VERSION`，形如 `v4.29.4+mtn1`），可据此确认当前运行的是维护分支。

## 4. 官方文档与本仓文档分工

| 查找内容 | 对应文档 |
|---|---|
| 面板操作、模型接入、平台适配器配置 | 官方文档 `docs/zh/use/`、`docs/zh/config/`，或 <https://docs.astrbot.app> |
| 插件开发基础（Star、指令、事件） | 官方 `docs/zh/dev/star/`，扩展接口结合 [`plugin-quickstart.md`](./plugin-quickstart.md) |
| 定时任务、主动型能力、MCP、知识库 | 官方 `docs/zh/use/` |
| 命令行参数 | 官方 `docs/zh/use/cli.md`；本分支仅版本号带 `+mtnN` 本地后缀 |
| 扩展 API 与新增配置项 | [`api-contract.md`](./api-contract.md)、[`api-reference.md`](./api-reference.md)、[`fork-advantages.md`](./fork-advantages.md) |

## 5. ⚠️ 不要从面板直接升级官方版本

面板的更新检查默认指向本仓库 Releases（`update_source` / `update_repository`），默认只提示本维护分支的发布版本。若将这两项改回官方地址，或在尚未同步该配置的旧实例上点击「升级」，上游 core 会覆盖本地受保护文件，导致扩展接口缺失或能力静默失效。跟进上游新版本时，请在本仓库内通过三方合并升级。

## 5.1 使用 AstrBot Launcher 时的注意事项

官方 AstrBot Launcher 将仓库地址、版本列表与面板下载地址固定指向 `AstrBotDevs/AstrBot`，高级设置仅支持配置代理与镜像源。使用启动器新建实例时，安装出的是上游官方版。

推荐使用 §2 的源码或 wheel 方式安装。若需保留启动器管理的存量实例，需先用启动器安装对应上游正式版，再将本分支的 core 文件同步到实例，并将面板部署到独立目录后通过 `ASTRBOT_WEBUI_DIR` 指定，具体步骤见 [`dashboard-build.md`](./dashboard-build.md)「使用 AstrBot Launcher 时」。该环境变量由 `main.py` 读取，使用 wheel 的 `astrbot run` 启动时无需设置。

## 6. 校验当前运行版本与文件完整性

```bash
python -c "import astrbot; print(astrbot.__version__)"
git for-each-ref --format='%(refname:short) -> %(*objectname:short)' refs/tags/baseline/
```

- 第一行输出当前维护版版本号（与 `maintained/VERSION` 一致，形如 `4.29.4+mtn1`）。`pyproject.toml`、`astrbot/__init__.py`（`__version__`）与 `maintained/VERSION` 三处版本字符串完全一致，由 `tests/maintained/test_version_marker.py` 校验；`+mtnN` 为 PEP 440 本地版本标记，严格 `Version()` 调用方使用 `astrbot.__version_base__`。
- 启动日志艺术字下方会打印 `AstrBot Maintained Fork` 及当前版本号。
- 第二行列出全部 `baseline/*` 锚点及其指向的上游提交，版本号最大的标签即为当前上游基线。锚点为附注标签，`%(*objectname:short)` 获取解引用后的目标提交；直接运行 `git rev-parse <tag>` 返回的是标签对象自身的哈希。

静态核对受保护文件的 SHA-256 哈希（无需启动实例）：

```bash
python -c "import hashlib,json,pathlib; f=json.load(open('maintained/installed_manifest.json',encoding='utf-8'))['files']; print('mismatch:', sum(hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()!=v for k,v in f.items()))"
```

期望输出 `mismatch: 0`。`maintained/installed_manifest.json` 逐条登记本分支改动过的 `astrbot/**` 文件哈希；针对运行实例的双端校验见 [`tools.md`](./tools.md)。

## 7. 配置与插件约定

- 插件位于 `data/plugins/<插件目录>/`，每个插件须包含 `metadata.yaml`；最小示例见 [`plugin-quickstart.md`](./plugin-quickstart.md)。
- 外部插件代码只应导入 `astrbot.api.*`，不要直接导入 `astrbot.core.*` 内部路径。
- 本分支新增的配置开关均位于面板 → 配置页，默认值保持上游行为。
- `proactive_capability.add_cron_tools` 默认开启，定时任务自唤醒行为与上游一致。
- 本仓库只发布 core 本体，不包含任何插件。

## 8. 常见问题排查入口

| 现象 | 排查入口 |
|---|---|
| 启动报错或扩展能力失效 | 查看 `data/logs/astrbot.log`，并运行 §6 的哈希核对命令校验受保护文件 |
| 查阅某个扩展 API 的签名与用法 | [`api-reference.md`](./api-reference.md)、[`api-contract.md`](./api-contract.md)、[`plugin-quickstart.md`](./plugin-quickstart.md) |
| 实例文件被覆盖后如何恢复 | [`tools.md`](./tools.md)（`check_drift.py` / `apply_patches.py`） |
| 使用启动器时面板被回滚为官方版 | [`dashboard-build.md`](./dashboard-build.md)「使用 AstrBot Launcher 时」 |
| 查看相对上游基线的变更内容 | [`CHANGELOG.md`](../../CHANGELOG.md)、[`fork-advantages.md`](./fork-advantages.md) |

当前可查阅的对外文档以 `docs/maintained/` 目录实际内容为准。
