# AstrBot 维护版（Maintained Fork）

> 官方 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的长期维护分支，基线锁定 `v4.28.2`。
> 上游插件无需修改即可运行，并在此基础上补充上游未提供的底层能力。
>
> A maintained fork of AstrBot pinned to the `v4.28.2` baseline: drop-in compatible
> with upstream plugins, plus a few extra low-level APIs.

---

## 项目定位

本仓库为**独立仓库**：不在 GitHub 的 fork 网络中，也不会向上游推送任何提交。我们的工作包括：

- 以上游 `v4.28.2` 为基线
- 修复缺陷、补充能力，并进行安全加固
- 保证上游插件无需修改即可运行

上游发布新版本后按需合并；基线本身不随上游升级而变动。

## 与上游版本的差异

可感知的差异如下。除**更新检查源**外，各项的默认值均与上游一致：

| 能力 | 默认（与上游一致） | 可选（本 fork 提供） |
|---|---|---|
| Python / Shell 执行授权 | 仅校验管理员权限 | `严格` 模式：还需在当前消息中明确要求“运行/执行”；引用文档中的“先编译，再运行”不再视为授权 |
| 完成钩子时序 | `原版`：回复先发出，钩子后触发 | `增强`：钩子先触发，审计与改写类逻辑可在回复发出前介入 |
| 核心暴露的扩展 API | — | `astrbot/api/**`：回合状态、交付策略、权限、媒体、运行时等（上游未提供） |
| QQ 消息聚合 | 与上游一致，默认 4 秒（`direct_turn_quiet_sec`） | 设为 0 关闭聚合，每条消息立即处理 |
| 轻量主动工具集 | 与上游一致，默认启用固定工具列表（`lightweight_proactive_tools`） | 可自定义该列表 |
| **更新检查源** | **指向本仓库**（上游默认指向上游官方） | 面板可改为跟随官方，见下 |

各项开关可在**面板 → 配置页**中调整，每项均附中文说明。

**本仓库只发布 core 本体，不随附任何插件。** 插件应作为独立项目单独获取与安装，
不在本仓库的打包或发布范围内。

## 安装与使用

当前版本 **`4.28.2+mtn1`**（`python -c "import astrbot; print(astrbot.__version__)"`）。

| 方式 | 命令 | 适用 |
|---|---|---|
| 源码 | `uv sync && uv run main.py` | 推荐；改代码、调试 |
| wheel | 从 [Releases](https://github.com/Chenamel/astrbot-maintained/releases) 下载 `.whl` | **当前唯一可用的 pip 安装方式**（尚未发布到 PyPI） |
| 容器 | 用本仓库 `Dockerfile` 自建镜像 | 部署 |
| 自建 wheel | `ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel` | **必须带此变量，否则不含 WebUI** |

分发名为 **`astrbot-maintained`**，与官方 `AstrBot` 在包管理器里是两份不同发行版；
但 **Python 导入名同为 `astrbot`**，所以同一环境只能留一份（先卸官方再装本 fork），
上游插件因此无需改动。

用 wheel 安装：

```bash
pip uninstall -y astrbot        # 装过官方包的先卸，否则文件会互相覆盖
pip install ./astrbot_maintained-4.28.2+mtn1-py3-none-any.whl
astrbot run                     # 启动后访问 http://localhost:6185
```

> 文件名含 `+`，部分 shell（尤其 PowerShell）会当作特殊字符。上面写成 `./文件名` 的形式，
> 或给整个文件名加引号，都可以绕开。

完整步骤（含容器注意事项、如何确认跑的是本 fork）见
[`docs/maintained/install.md`](./docs/maintained/install.md)。

### 关于“检查更新”

面板的更新检查**默认指向本仓库的 Releases**，因此只会提示本维护版的版本，
不会出现上游 `4.29.x`——也就不存在“点一下就被覆盖成上游代码”的风险。

若你确实想离开本 fork、改回跟随官方，可在**面板 → 配置 → 系统**里把
`更新检查地址` 改为 `https://api.soulter.top/releases`，`更新来源仓库` 改为
`https://github.com/AstrBotDevs/AstrBot`。两者要指向同一个项目。

> 这个默认值与上游不同（上游指向官方）。这是本 fork 唯一一处**故意偏离默认值**的地方，
> 理由是：上游版本对插件的行为与本 fork 不兼容，把它作为升级目标是危险的。

## 面向插件开发者

- 新增能力全部落在 `astrbot/api/**`，外部仅需 `import astrbot.api.*`
- `astrbot.api.*` 及插件实际依赖的 core 路径均已冻结，不会在次要版本中变更
- 如需使用新增能力（查询回合状态、判断执行权限等），可查阅 `astrbot/api/` 下的对应模块

## 常见问题

**上游插件可以直接使用吗？**
可以。硬约束是「上游插件不改也能跑」；在此前提下，本 fork 允许调整 core、WebUI 与默认值，
但每处改动都要求动机可解释、可维护，并非无条件退守上游行为。

**能否升级到上游最新版本？**
不建议直接升级。我们按自身节奏合并上游改动；也可自行合并（参见维护者文档）。
面板的更新检查已默认指向本仓库，正常情况下不会提示上游版本。

**发现缺陷或有功能建议？**
欢迎直接提交 issue，建议附上日志（默认位于 `data/logs/astrbot.log`）。

**维护者的施工记录去哪了？**
不在本仓库内。本仓库只含可交付的 core 与面向使用者的文档；内部台账与施工日志随维护者本地保留。

## 文档导航

| 需要了解的内容 | 位置 |
|---|---|
| 维护者向说明（基线、台账、上游同步） | [`README_MAINTAINED.md`](./README_MAINTAINED.md) |
| 安装说明 | [`docs/maintained/install.md`](./docs/maintained/install.md) |
| 插件作者 5 分钟入门 | [`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md) |
| API 契约与能力说明 | [`docs/maintained/`](./docs/maintained/)（api-contract / fork-advantages / design / proposal / tools） |
| 相对上游的改动清单 | [`CHANGELOG.md`](./CHANGELOG.md) |
| core 改动台账（SHA-256，可脚本校验） | [`maintained/installed_manifest.json`](./maintained/installed_manifest.json) |
| 上游官方说明 | [`README_zh.md`](./README_zh.md) 等，或 [上游仓库](https://github.com/AstrBotDevs/AstrBot) |

## 许可证

AGPL-3.0-or-later，与上游一致；完整文本见 [`LICENSE`](./LICENSE)（未改动）。
本 fork 与 AstrBot 作者无从属或背书关系。
