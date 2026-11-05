# 安装与运行

本页说明如何把 **AstrBot 维护版 fork** 跑起来。基线锁定上游 `v4.28.2`，配置文件格式与
上游兼容，已安装的上游插件无需修改即可继续使用。想先了解"比官方多了什么"，请先读
[`fork-advantages.md`](./fork-advantages.md)。

## 1. 准备

- Python **3.12 或更高**（`pyproject.toml` 的 `requires-python = ">=3.12"`）
- `uv`（仓库用 `uv sync` 管理依赖）
- git

Windows / macOS / Linux 均可。

## 2. 源码启动

clone 本仓库并进入仓库根目录后：

```bash
uv sync
uv run main.py
```

启动后：

- WebUI 地址 `http://localhost:6185`，平台适配器、模型、插件开关都在**面板 → 配置页**设置。
- 配置、插件、日志等运行时数据落在仓库的 `data/` 目录，该目录不入库。
- 首次使用按面板引导完成初始化即可；配置文件格式与上游 `v4.28.2` 兼容。

## 3. ⚠️ 不要点「升级到新版本」

面板顶部若提示「AstrBot 有新版本」，**请勿升级**。该提示指向上游 `v4.29+`，升级会用
上游 core 覆盖本 fork 的改动；受保护文件缺失时，实例侧会出现 `ImportError` 或能力静默失效。
需要跟进上游版本时，请在本仓库内做三方合并，而不是通过面板就地升级。

## 4. 容器部署要注意镜像来源

仓库根目录的 `compose.yml` 引用的是**上游官方镜像** `soulter/astrbot:latest`：直接
`docker compose up` 跑起来的是上游，不是本 fork。

如需容器部署，请基于仓库根目录的 `Dockerfile` 自行构建包含本仓库代码的镜像，并保持：

- 映射 WebUI 端口 `6185`；
- 把 `data/` 持久化到容器内 `/AstrBot/data`（配置、插件、日志都在这里）。

本仓库没有发布自有的公共镜像 tag，因此不在此给出镜像名。

## 5. 怎么确认跑的是本 fork

```bash
python -c "import astrbot; print(astrbot.__version__)"
git rev-parse 'baseline/v4.28.2^{commit}'
```

- 第一行应为 `4.28.2+mtn1`。`pyproject.toml` 里写的是 `4.28.2`（无 `+mtn1`）属**有意设计**：
  包版本号必须能被 PEP 440 严格解析，两者由 `tests/maintained/test_version_marker.py` 钉住。
- 第二行应为 `3c7adafa…`（上游 `v4.28.2` 的基线提交）。`baseline/v4.28.2` 是附注标签，
  直接 `git rev-parse baseline/v4.28.2` 返回的是标签对象自身的 id，加 `^{commit}` 才是提交；
  该锚点永久存在，供回滚与三方合并比对。

再核对受保护文件的哈希（纯静态，不需要运行中的实例或面板）：

```bash
python -c "import hashlib,json,pathlib; f=json.load(open('maintained/installed_manifest.json',encoding='utf-8'))['files']; print('mismatch:', sum(hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()!=v for k,v in f.items()))"
```

期望输出 `mismatch: 0`。台账共 62 条（52 个 core 文件 + 10 个 `astrbot/api` 文件），
逐条登记本 fork 改动过的文件；实例侧的双端校验见 [`tools.md`](./tools.md)。

## 6. 插件与配置

- 插件放在 `data/plugins/<插件目录>/`，每个插件需要自己的 `metadata.yaml`；
  5 分钟写一个最小插件见 [`plugin-quickstart.md`](./plugin-quickstart.md)。
- **外部代码只允许 `import astrbot.api.*`**，不要直接依赖 `astrbot.core.**` 私有路径。
- 本 fork 新增的开关都在面板 → 配置页，并附中文说明；默认值与上游一致。
- **主动型能力与上游一致**：`proactive_capability.add_cron_tools` 默认开启，定时任务自唤醒正常工作。
- **本仓库只发布 core 本体，不包含任何插件**；插件不在打包与发布范围内。

## 7. 出问题看哪

| 现象 | 先看哪里 |
|---|---|
| 启动报错 / 能力失效 | `data/logs/astrbot.log`，再用 §5 的哈希命令核对受保护文件 |
| 不知道某个 API 怎么用 | [`api-contract.md`](./api-contract.md)（唯一规格来源）、[`plugin-quickstart.md`](./plugin-quickstart.md) |
| 想知道补丁被覆盖后怎么恢复 | [`tools.md`](./tools.md)（`check_drift.py` / `apply_patches.py`） |
| 想知道相对上游改了什么 | [`CHANGELOG.md`](../../CHANGELOG.md)、[`README_MAINTAINED.md`](../../README_MAINTAINED.md) |

`CHANGELOG.md` 是逐阶段施工台账，其中提到的部分内部文档不随公开仓库分发；当前可查阅的
对外文档以 `docs/maintained/` 目录实际内容为准。
