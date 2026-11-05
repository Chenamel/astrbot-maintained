# 安装与运行

本页说明如何把 **AstrBot 维护版 fork** 跑起来。基线锁定上游 `v4.28.2`，配置文件格式与
上游兼容，已安装的上游插件无需修改即可继续使用。想先了解"比官方多了什么"，请先读
[`fork-advantages.md`](./fork-advantages.md)。

> **本仓库只发布 core 本体，不包含任何插件。** 插件需另行获取与安装，不在本仓库的
> 打包与发布范围内。本文只讲 core 怎么装、怎么确认装对了。
>
> 面板使用、平台适配器配置、模型接入、插件开发等**通用内容不在本文重复**，请看官方文档
> （仓库内自带副本：`docs/zh/`，或 <https://docs.astrbot.app>）。本文只写**本 fork 特有的部分**。

## 1. 准备

- Python **3.12 或更高**（`pyproject.toml` 的 `requires-python = ">=3.12"`）
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

### 方式 B：pip 安装（当库用，不推荐跑服务）

本 fork 以 `astrbot-maintained` 为分发名发布，**与官方的 `astrbot` 是不同包名**，
不会互相覆盖：

```bash
pip install astrbot-maintained
astrbot run
```

> 为什么改名：官方包名是 `AstrBot`。若沿用同名，`pip install` 两个包会互相覆盖，
> 装完之后无法判断跑的是哪一份。本项目把分发名固定为 `astrbot-maintained`，
> 但**Python 导入名仍是 `astrbot`**（`import astrbot` 不变），所以上游插件无需改动。

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
- 首次使用按面板引导完成初始化即可；配置文件格式与上游 `v4.28.2` 兼容。
- 启动日志的艺术字下方会多一行 **`AstrBot Maintained Fork v4.28.2+mtn1`**——
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

面板顶部若提示「AstrBot 有新版本」，**请勿升级**。该提示指向上游 `v4.29+`，升级会用
上游 core 覆盖本 fork 的改动；受保护文件缺失时，实例侧会出现 `ImportError` 或能力静默失效。
需要跟进上游版本时，请在本仓库内做三方合并，而不是通过面板就地升级。

## 6. 怎么确认跑的是本 fork

```bash
python -c "import astrbot; print(astrbot.__version__)"
git rev-parse 'baseline/v4.28.2^{commit}'
```

- 第一行应为 `4.28.2+mtn1`。`pyproject.toml`、`astrbot/__init__.py`、`maintained/VERSION`
  三处版本号**完全一致**，由 `tests/maintained/test_version_marker.py` 钉住；
  `+mtnN` 是 PEP 440 允许的本地版本标记，也是 pip 包名之后第二重身份标识。
- 启动日志艺术字下方会多一行 `AstrBot Maintained Fork v4.28.2+mtn1`，官方版本没有这一行。
- 第二行应为 `3c7adafa…`（上游 `v4.28.2` 的基线提交）。`baseline/v4.28.2` 是附注标签，
  直接 `git rev-parse baseline/v4.28.2` 返回的是标签对象自身的 id，加 `^{commit}` 才是提交；
  该锚点永久存在，供回滚与三方合并比对。

再核对受保护文件的哈希（纯静态，不需要运行中的实例或面板）：

```bash
python -c "import hashlib,json,pathlib; f=json.load(open('maintained/installed_manifest.json',encoding='utf-8'))['files']; print('mismatch:', sum(hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()!=v for k,v in f.items()))"
```

期望输出 `mismatch: 0`。台账共 62 条（52 个 core 文件 + 10 个 `astrbot/api` 文件），
逐条登记本 fork 改动过的文件；实例侧的双端校验见 [`tools.md`](./tools.md)。

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
| 想知道相对上游改了什么 | [`CHANGELOG.md`](../../CHANGELOG.md)、[`README_MAINTAINED.md`](../../README_MAINTAINED.md) |

`CHANGELOG.md` 是逐阶段施工台账，其中提到的部分内部文档不随公开仓库分发；当前可查阅的
对外文档以 `docs/maintained/` 目录实际内容为准。
