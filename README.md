# AstrBot 维护版（Maintained Fork）

> 官方 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的长期维护分支，锁定在 `v4.28.2` 基线。
> 上游插件不用改就能跑，另加一批上游没有的底层 API。
>
> A maintained fork of AstrBot pinned to the `v4.28.2` baseline: drop-in compatible
> with upstream plugins, plus low-level APIs upstream does not provide.

---

## 我为什么在看这个 fork

如果你已经在用官方版，只需要看你是否遇到过下面任意一条：

- 写插件想拿到**当前回合的完整上下文**（这条消息被合并过没有、原文是什么），只能自己扒事件对象；
- 想让 bot **主动开口**，但 `Context.llm_generate` 出来的话没有人格、没有长期记忆——因为它绕过了 `on_llm_request`；
- 想在**回复发出之前**拦截改写，但官方钩子在回复之后才触发，只能事后补救；
- 想判断这次调用**到底有没有执行授权**，官方只给"是不是管理员"。

这几条需求都源自同一件事：**官方没有对外暴露这些底层状态**。本 fork 把它们做成 `astrbot/api/**`。

如果你只是装个 bot 日常聊天、不写插件，那说实话——**这个 fork 对你没什么用**。
官方版更适合你，更新也快。

## 和官方版的核心区别

| 维度 | 官方 AstrBot | 本 fork |
|---|---|---|
| 基线 | 持续跟进 | **锁 `v4.28.2`**，只按需合并上游改动 |
| 插件兼容 | — | 硬约束：**上游插件不改也能跑** |
| 扩展 API | 仅 `Context` 等高层接口 | 另有 `astrbot/api/**`：**新增 10 个模块**，暴露回合、交付、权限、媒体等底层状态 |
| 运行行为 | — | **默认与上游一致**，新能力都要主动开启 |
| 更新检查 | 指向官方 Releases | **指向本仓库**（唯一一处故意不同的默认值，原因见下） |

一句话：**它不是"更好的 AstrBot"，是"给插件作者多开了一层接口的 AstrBot"。**

> **看到"后门"字样？那是旧版本的说法。**
>
> 本 README 在 `v4.28.2+mtn1` 首个公开版里曾把这层接口写成"后门"，现已统一改为"**接口**"。
> 如果你是在镜像站、搜索引擎快照或较早的缓存页里看到"后门"两个字，那不是现在的表述。
> 这些模块是公开、有文档、可逐行审查的 Python API（源码在 `astrbot/api/**`，
> 调用手册见 [`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)），
> 不涉及任何绕过鉴权的隐蔽入口。

## 新增了什么

### 1. `astrbot/api/**`：新增 10 个模块

每个模块都有 `available()`，在纯上游环境返回 `False`——插件可以先判断再调用，**同一份代码在官方版和本 fork 上都能跑**。

| 模块 | 解决什么 | 主要接口 |
|---|---|---|
| `api.turns` | 回合状态：这条事件还算不算当前回合、合并后的原文与图片 | `is_current` / `merged_text` / `merged_image_urls` / `mark_sent` |
| `api.proactive` | **走人格链生成主动回复**（见下） | `generate_with_persona` / `persona_available` |
| `api.delivery` | 交付策略：该发文字还是发文件、代码任务怎么描述 | `resolve` / `has_code_delivery` / `code_task_spec` |
| `api.permissions` | 执行授权判定（区分"是管理员"与"本次被授权执行"） | `execution_denial` / `is_admin` |
| `api.media` | 视觉输入是否可用、图片是否带说明 | `has_visual_input` / `image_input_available` / `has_image_caption` |
| `api.content` | 消息段类型判定（文字 / 图片） | `is_text_part` / `is_image_part` |
| `api.runtime` | 路径、时间格式化、下载图片、钩子时序模式 | `get_astrbot_data_path` / `download_image_by_url` / `hook_timing_mode` |
| `api.embedding` | 向量化调用 | `is_embedding_provider` |
| `api.event.extras` | 事件对象的附加信息 | 见 api-contract |
| `api._bridge` | 内部桥接层（插件不应直接用） | — |

每个函数的参数、返回值、调用示例和坑，都写在
[`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)。

> `astrbot/api/` 下还有 `provider` / `platform` / `star` / `util` 等子包，是**上游原有能力**的薄封装再导出，不是本 fork 新增。

**`generate_with_persona` 值得单独说。** 官方 `Context.llm_generate` 直接调 provider、跳过 `on_llm_request`，所以你装的人格插件、记忆插件对它生成的内容**完全不生效**——主动回复常常"不像本人"。这个接口先走一遍钩子再生成，人格与记忆能正常参与。

### 2. 四个可选开关（默认全部等于上游）

| 面板里的名字 | 配置键 | 默认 | 打开后 |
|---|---|---|---|
| 执行授权模式 | `execution_gate_mode` | `legacy` | 改 `strict`：还需当前消息明确要求"运行/执行"，引用文档里的"先编译再运行"不再算授权 |
| 完成钩子时序 | `hook_timing_mode` | `legacy` | 改 `enhanced`：钩子先于回复触发，可在发出前拦截改写 |
| QQ 消息聚合窗口（秒） | `direct_turn_quiet_sec` | `4` | 设 `0` 关闭聚合，每条消息立即处理 |
| 轻量主动工具集 | `lightweight_proactive_tools` | 固定列表（29 项） | 可自定义该列表 |

**这四个都是 fork 新增的键**，上游配置文件里没有。不改就一直走上游行为。

### 3. 两处会看到但不用管的差异

- 启动日志在 ASCII 艺术字下方多一行 `AstrBot Maintained Fork v4.28.2+mtn1`，官方版没有；
- 分发包名是 `astrbot-maintained`，但 **Python 导入名仍是 `astrbot`**——这是刻意的，正因为如此上游插件不用改。

## 兼容性：我实测过的事

**插件版本声明照常生效。** 插件市场按 PEP 440 判 `astrbot_version`，`4.28.2+mtn1` 的 `+mtn1` 是 local 段，**在版本区间比较中被忽略**：

| 插件声明 | 在 `4.28.2+mtn1` 下 |
|---|---|
| `>=4.16,<5`（市场最常见） | ✅ 兼容 |
| `>=4.28.2` / `==4.28.2` / `~=4.28.0` | ✅ 兼容 |
| `>=4.29` / `<4.28` | ❌ 正确拒绝 |

唯一例外是 `===4.28.2`（三等号严格相等）会判否——PEP 440 标准行为，市场基本不这么写。

**上游测试全绿。** 相对基线零改动，2949 passed / 6 skipped / 2 项已登记的 xfail。

## 快速上手

当前版本 **`4.28.2+mtn1`**。

### 用 wheel（推荐）

从 [Releases](https://github.com/Chenamel/astrbot-maintained/releases) 下载 `.whl`：

```bash
pip uninstall -y astrbot      # 装过官方版的先卸，否则文件互相覆盖
pip install ./astrbot_maintained-4.28.2+mtn1-py3-none-any.whl
astrbot run
```

访问 `http://localhost:6185`。

> 文件名带 `+`，PowerShell 会当成特殊字符。写成 `./文件名` 或整体加引号即可。
> **尚未发布到 PyPI**，`pip install astrbot-maintained` 会 404。

### 从源码

```bash
uv sync && uv run main.py
```

### 自己打 wheel

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

**这个变量必须带**，否则产物里没有 WebUI，装完打开面板是空白。

> 完整步骤（含容器、如何确认跑的是本 fork）见 [`docs/maintained/install.md`](./docs/maintained/install.md)。

## 注意事项

### 更新检查默认指向本仓库，不是官方

这是本 fork **唯一一处故意偏离上游默认值**的地方。

原因：上游 `4.29+` 是另一套代码，本 fork 的 API 在那边不存在。把上游当升级目标，等于给用户一个"一点就毁"的按钮。

想离开本 fork 改回跟随官方，在**面板 → 配置 → 系统**里把：

- `更新检查地址` 填 `https://api.soulter.top/releases`
- `更新来源仓库` 填 `https://github.com/AstrBotDevs/AstrBot`

两者要指向同一个项目。

### 不要追上游 `master`

锁基线是刻意选择。需要上游的新修复，等本仓库合并，或自己 cherry-pick。

### 本仓库只发 core，不含任何插件

`pip` 装完是干净的核心，插件各自独立安装。

### 基线是 `v4.28.2`，不是上游最新

这是当前状态，不是失误。评估时请按 `4.28.2` 的能力算，不要拿上游 `4.29+` 的功能对照。

## 给插件作者

- 新能力全在 `astrbot/api/**`，外部只 `import astrbot.api.*`；
- 用 `available()` 判断能力是否存在，让同一份代码在官方版上也能优雅退化：

```python
from astrbot.api import proactive

if proactive.available() and proactive.persona_available():
    resp = await proactive.generate_with_persona(context, event, "说点什么")
else:
    resp = await context.llm_generate(prompt="说点什么")   # 官方版路径
```

- 5 分钟入门：[`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md)

## 常见问题

**上游插件能直接用吗？**
能。这是硬约束，不是"尽量"。

**改了插件调用方式吗？**
没有。新增是 additive 的，原有 `Context` 接口一个没动。

**能升级到上游最新版吗？**
不建议。面板也不会提示——更新检查地址指向本仓库。要跟上游请自行合并。

**出问题在哪反馈？**
直接提 issue，附 `data/logs/astrbot.log`。

## 文档导航

| 想知道 | 位置 |
|---|---|
| 安装细节、容器、确认跑的是本 fork | [`docs/maintained/install.md`](./docs/maintained/install.md) |
| 插件作者入门 | [`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md) |
| **API 调用手册（参数、返回值、示例）** | [`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md) |
| API 契约（设计约束、降级机制） | [`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md) |
| 为什么这么设计 | [`docs/maintained/design.md`](./docs/maintained/design.md) |
| 相对上游改了什么 | [`CHANGELOG.md`](./CHANGELOG.md) |
| 维护者向（基线、台账、合并流程） | [`README_MAINTAINED.md`](./README_MAINTAINED.md) |
| core 改动台账（SHA-256，可脚本校验） | [`maintained/installed_manifest.json`](./maintained/installed_manifest.json) |
| 上游官方说明 | [`README_zh.md`](./README_zh.md) |

## 许可证

AGPL-3.0-or-later，与上游一致；全文见 [`LICENSE`](./LICENSE)（未改动）。

本 fork 与 AstrBot 作者无从属或背书关系。
