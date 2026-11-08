# 安装与运行

本页说明如何把 AstrBot 维护版 fork 跑起来。基线锁定上游 `v4.29.4`，配置文件格式与
上游兼容，已安装的上游插件无需修改即可继续使用。想先了解"比官方多了什么"，请先读
[`fork-advantages.md`](./fork-advantages.md)。

> 本仓库只发布 core 本体，不包含任何插件。 插件需另行获取与安装，不在本仓库的
> 打包与发布范围内。本文只讲 core 怎么装、怎么确认装对了。
>
> 面板使用、平台适配器配置、模型接入、插件开发等通用内容不在本文重复，请看官方文档
> （仓库内自带副本：`docs/zh/`，或 <https://docs.astrbot.app>）。本文只写本 fork 特有的部分。

## 1. 准备

- Python 3.12 或更高（`pyproject.toml` 的 `requires-python = ">=3.12"`）
- `uv`（仓库用 `uv sync` 管理依赖）
- git

Windows / macOS / Linux 均可。

## 2. 三种安装方式，选一种

### 方式 A：源码运行（推荐，改代码/调试用）

clone 本仓库并进入仓库根目录后：

```bash
uv sync
uv run main.py
```

### 方式 B：wheel 安装

从 [Releases](https://github.com/Chenamel/astrbot-maintained/releases) 下载 `.whl` 后：

```bash
pip uninstall -y astrbot        # 装过官方包的先卸，否则文件互相覆盖
pip install ./astrbot_maintained-4.29.4+mtn1-py3-none-any.whl
astrbot run
```

> 文件名含 `+`，部分 shell（尤其 PowerShell）会当作特殊字符。写成 `./文件名`，
> 或给整个文件名加引号，都可以绕开。
>
> **尚未发布到 PyPI。** 本 fork 的分发名固定为 `astrbot-maintained`，与官方 `AstrBot`
> 不重名；但**Python 导入名同为 `astrbot`**（`import astrbot` 不变，上游插件无需改动）
> 这意味着**同一个环境里只能留一份**，装本 fork 前先卸掉官方包。
>
> ⚠️ **wheel 必须带 WebUI 才有面板**。官方发布的 wheel 里包含
> `astrbot/dashboard/dist/`（Vue 构建产物）。自行构建时必须显式开启：
>
> ```bash
> ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
> ```
>
> 不带该变量构建出的 wheel **不含面板**，`astrbot run` 起来后访问 6185 端口拿不到界面。
> 构建前置：Node.js + npm（`dashboard/` 用 pnpm 10 锁文件，详见
> [`dashboard-build.md`](./dashboard-build.md)）。校验方法：
> `python -c "import zipfile,glob;z=zipfile.ZipFile(glob.glob('*.whl')[0]);print(sum('dashboard/dist/' in n for n in z.namelist()))"`
> 应输出大于 0 的数字（完整构建约 272）。

### 方式 C：容器（需自行构建镜像）

仓库根目录的 `compose.yml` 引用的是**上游官方镜像** `soulter/astrbot:latest`：
直接 `docker compose up` 跑起来的是官方版本，不是本 fork。

如需容器部署，请基于仓库根目录的 `Dockerfile` 自行构建：

```bash
docker build -t astrbot-maintained:local .
docker run -d --name astrbot -p 6185:6185 \
  -v /path/to/data:/AstrBot/data astrbot-maintained:local
```

本仓库**没有**发布公共镜像 tag，因此这里不给镜像名。

## 3. 启动后

- WebUI 地址 `http://localhost:6185`，平台适配器、模型、插件开关都在**面板 → 配置页**设置。
- 配置、插件、日志等运行时数据落在仓库的 `data/` 目录，该目录不入库。
- 首次使用按面板引导完成初始化即可；配置文件格式与上游 `v4.29.4` 兼容。
- 启动日志的艺术字下方会多一行 **`AstrBot Maintained Fork v4.29.4+mtn1`**：
  官方版本没有这一行，可据此快速确认跑的是本 fork。

## 4. 哪些内容请直接看官方文档

| 想知道 | 看哪里 |
|---|---|
| 面板怎么用、模型怎么接、平台适配器怎么配 | 官方文档 `docs/zh/use/`、`docs/zh/config/`，或 <https://docs.astrbot.app> |
| 插件开发入门（Star、指令、事件） | 官方 `docs/zh/dev/star/`，再结合本仓库 [`plugin-quickstart.md`](./plugin-quickstart.md) 里 fork 新增的 api |
| 定时任务、主动型能力、MCP、知识库 | 官方 `docs/zh/use/`（本 fork 与上游一致） |
| 命令行参数 | 官方 `docs/zh/use/cli.md`；本 fork 仅版本号带 `+mtnN` 后缀 |
| 本 fork 新增的 api 与配置项 | [`api-contract.md`](./api-contract.md)、[`fork-advantages.md`](./fork-advantages.md) |

## 5. ⚠️ 不要点「升级到新版本」

面板的更新检查默认指向本仓库的 Releases（`update_source` /
`update_repository`），因此只会提示本维护版的版本，不会出现上游 `v4.29+`。
把这两项改回官方地址（或运行尚未同步该配置的旧实例）后，面板才会出现
「AstrBot 有新版本」，**此时请勿升级**：上游 core 会覆盖本 fork 的改动，
受保护文件缺失时会出现 `ImportError` 或能力静默失效。
需要跟进上游版本时，请在本仓库内做三方合并，而不是通过面板就地升级。

## 5.1 AstrBot Launcher 不能用来安装本 fork

官方的 AstrBot Launcher 把仓库地址写死为 `AstrBotDevs/AstrBot`，版本列表、
面板下载地址同样写死；高级设置里只有代理和镜像源，没有自定义仓库或版本源
的开关。用它新建实例，装出来的一定是**上游官方版**，不是本 fork。

正确做法是改用 §2 的 wheel 或源码方式安装。若一定要保留启动器管理的实例，
只能先用它装好官方 `v4.29.4`，再手工把本 fork 的 core 文件与面板覆盖进去；
这类改造后面板会被启动器按版本校验回滚，需要把 fork 面板放到独立目录并用
`ASTRBOT_WEBUI_DIR` 指定，步骤见 [`dashboard-build.md`](./dashboard-build.md)
「使用 AstrBot Launcher 时」。注意该环境变量由启动入口 `main.py` 读取，
通过 wheel 的 `astrbot run` 启动时不需要它（wheel 已内置面板）。

## 6. 怎么确认跑的是本 fork

```bash
python -c "import astrbot; print(astrbot.__version__)"
git rev-parse 'baseline/v4.29.4^{commit}'
```

- 第一行应为 `4.29.4+mtn1`。`pyproject.toml`、`astrbot/__init__.py`、`maintained/VERSION`
  三处版本号**完全一致**，由 `tests/maintained/test_version_marker.py` 钉住；
  `+mtnN` 是 PEP 440 允许的本地版本标记，也是 pip 包名之后第二重身份标识。
- 启动日志艺术字下方会多一行 `AstrBot Maintained Fork v4.29.4+mtn1`，官方版本没有这一行。
- 第二行应为 `3c7adafa…`（上游 `v4.29.4` 的基线提交）。`baseline/v4.29.4` 是附注标签，
  直接 `git rev-parse baseline/v4.29.4` 返回的是标签对象自身的 id，加 `^{commit}` 才是提交；
  该锚点永久存在，供回滚与三方合并比对。

再核对受保护文件的哈希（纯静态，不需要运行中的实例或面板）：

```bash
python -c "import hashlib,json,pathlib; f=json.load(open('maintained/installed_manifest.json',encoding='utf-8'))['files']; print('mismatch:', sum(hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()!=v for k,v in f.items()))"
```

期望输出 `mismatch: 0`。台账共 68 条，逐条登记本 fork 改动过的 `astrbot/**`
文件；实例侧的双端校验见 [`tools.md`](./tools.md)。

## 7. 配置与插件

- 插件放在 `data/plugins/<插件目录>/`，每个插件需要自己的 `metadata.yaml`；
  5 分钟写一个最小插件见 [`plugin-quickstart.md`](./plugin-quickstart.md)。
- **外部代码只允许 `import astrbot.api.*`**，不要直接依赖 `astrbot.core.**` 私有路径。
- 本 fork 新增的开关都在面板 → 配置页，并附中文说明；默认值与上游一致。
- **主动型能力与上游一致**：`proactive_capability.add_cron_tools` 默认开启，定时任务自唤醒正常工作。
- **本仓库只发布 core 本体，不包含任何插件**；插件不在打包与发布范围内。

## 8. 出问题看哪

| 现象 | 先看哪里 |
|---|---|
| 启动报错 / 能力失效 | `data/logs/astrbot.log`，再用 §6 的哈希命令核对受保护文件 |
| 不知道某个 API 怎么用 | [`api-contract.md`](./api-contract.md)（唯一规格来源）、[`plugin-quickstart.md`](./plugin-quickstart.md) |
| 想知道补丁被覆盖后怎么恢复 | [`tools.md`](./tools.md)（`check_drift.py` / `apply_patches.py`） |
| 用启动器装出来的是官方版 / 面板被覆盖 | [`dashboard-build.md`](./dashboard-build.md)「使用 AstrBot Launcher 时」 |
| 想知道相对上游改了什么 | [`CHANGELOG.md`](../../CHANGELOG.md)、[`fork-advantages.md`](./fork-advantages.md) |

`CHANGELOG.md` 是逐阶段施工台账，其中提到的部分内部文档不随公开仓库分发；当前可查阅的
对外文档以 `docs/maintained/` 目录实际内容为准。
