![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

<a href="./README.md">English</a> ｜ 简体中文 ｜ <a href="./README_zh-TW.md">繁體中文</a> ｜ <a href="./README_ja.md">日本語</a> ｜ <a href="./README_fr.md">Français</a> ｜ <a href="./README_es.md">Español</a> ｜ <a href="./README_ru.md">Русский</a>

<br>
<br>

[![version](https://img.shields.io/badge/version-4.28.2%2Bmtn1-blue)](https://github.com/Chenamel/astrbot-maintained/releases)
[![license](https://img.shields.io/badge/license-AGPL--3.0-green)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

</div>

这是 AstrBot 的维护分支，基线锁定在上游 `v4.28.2` 版本。仓库独立维护，不在 GitHub 的 fork 网络里。分发包只包含 core 本体，不含插件。许可证是 AGPL-3.0-or-later，与上游作者无从属关系。

## 核心差异与新增 API

上游官方版本没有公开部分底层状态。这个 fork 在 `astrbot/api/**` 下补了接口，把这些状态开放出来。

`astrbot/api/` 下共有 10 个新增或变动文件，其中 8 个是功能模块，2 个是辅助文件。每个功能模块都提供 `available()` 函数。在上游原版环境中，`available()` 返回 `False`。

| 模块 | 职责说明 | 主要接口 |
|---|---|---|
| `api.turns` | 回合状态判定，获取合并后的原文与图片 | `is_current` / `merged_text` / `merged_image_urls` / `mark_sent` |
| `api.proactive` | 接入人格与记忆链的主动回复生成 | `generate_with_persona` / `persona_available` |
| `api.delivery` | 交付策略判定，区分文本消息与文件交付 | `resolve` / `has_code_delivery` / `code_task_spec` |
| `api.permissions` | 执行授权判定，区分管理员身份与本次执行授权 | `execution_denial` / `is_admin` |
| `api.media` | 视觉输入可用性判定与图片说明检测 | `has_visual_input` / `image_input_available` / `has_image_caption` |
| `api.content` | 消息段类型判定 | `is_text_part` / `is_image_part` |
| `api.runtime` | 运行路径、时间格式化、图片下载与时序模式 | `get_astrbot_data_path` / `download_image_by_url` / `hook_timing_mode` |
| `api.embedding` | 向量化提供方判定 | `is_embedding_provider` |
| `api.event.extras` | 事件附加信息载体 | 见事件附加协议 |
| `api._bridge` | 内部桥接层，供模块间协调，插件不应直接调用 | — |

上游原版的 `Context.llm_generate` 直接调用底层模型提供方，跳过了 `on_llm_request` 钩子，人格与记忆插件因此失效。`generate_with_persona` 会先执行请求钩子，让这两个插件照常参与进来。

## 配置项

新增了 4 个配置项，默认值都与上游官方行为一致。

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `execution_gate_mode` | `legacy` | 执行授权模式。默认与上游一致；设为 `strict` 要求消息显式请求执行 |
| `hook_timing_mode` | `legacy` | 完成钩子触发时序。设为 `enhanced` 时钩子在回复发出前触发 |
| `direct_turn_quiet_sec` | `4` | QQ 消息聚合静默窗口秒数。设为 `0` 则关闭聚合立即处理 |
| `lightweight_proactive_tools` | 列表（共 29 项） | 轻量主动工具集白名单列表 |

## 兼容性

版本号是 `4.28.2+mtn1`。其中 `+mtn1` 是 PEP 440 的 local 段，在版本区间比较时会被忽略。

| 声明方式 | 示例 | 兼容判定 |
|---|---|---|
| 区间声明 | `>=4.16,<5` | 兼容 |
| 基线匹配 | `==4.28.2`、`~=4.28.0` | 兼容 |
| 高版本要求 | `>=4.29` | 拒绝 |
| 严格等号匹配 | `===4.28.2` | 拒绝（PEP 440 规则要求字符串全量相等） |

针对基线的测试中，维护版测试通过 608 项；上游测试通过 2949 项，跳过 6 项，已登记 xfail 2 项。

## 安装与运行

环境要求 Python 3.12 或更高版本。

尚未发布到 PyPI，`pip install astrbot-maintained` 装不上。

分发包名为 `astrbot-maintained`，Python 导入名同为 `astrbot`。安装前先卸官方版，避免导入名冲突。

### 使用 wheel 安装

从 Releases 页面下载 `.whl` 文件。文件名带 `+` 字符，在部分 shell 中需要引号包裹或转义：

```bash
pip uninstall -y astrbot
pip install ./astrbot_maintained-4.28.2+mtn1-py3-none-any.whl
astrbot run
```

安装后启动，浏览器访问 `http://localhost:6185` 进入管理面板。

### 源码运行

克隆本仓库后使用 `uv` 运行：

```bash
uv sync && uv run main.py
```

### 自行构建 wheel

自行构建包含 WebUI 面板的 wheel 产物时，需要指定构建环境变量：

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

未设置该环境变量时，构建产物不会包含 WebUI 静态文件。

## 更新检查与上游同步

面板的更新检查默认指向本仓库 Releases：

- `update_source`: `https://api.github.com/repos/Chenamel/astrbot-maintained/releases`
- `update_repository`: `https://github.com/Chenamel/astrbot-maintained`

上游 `v4.29+` 架构已变更，没有这里新增的底层 API。若从面板直接更新到官方版本，修改过的核心文件会被覆盖，导致接口缺失与运行异常。

若需要恢复跟随官方更新，在管理面板中将 `update_source` 修改为 `https://api.soulter.top/releases`，将 `update_repository` 修改为 `https://github.com/AstrBotDevs/AstrBot`。

## 文档

- 安装细节、容器部署、如何确认跑的是本 fork：[`docs/maintained/install.md`](./docs/maintained/install.md)
- 插件作者 5 分钟入门：[`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md)
- 每个 API 的参数、返回值、调用示例：[`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)
- API 设计约束与降级机制：[`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md)
- 为什么这样分层：[`docs/maintained/design.md`](./docs/maintained/design.md)
- 相对上游改了什么：[`CHANGELOG.md`](./CHANGELOG.md)
- core 改动台账（SHA-256，可脚本校验）：[`maintained/installed_manifest.json`](./maintained/installed_manifest.json)

## 关于历史表述

本 README 早期把这层接口叫过“后门”，现在统一叫“接口”。

镜像站和搜索缓存里可能还是旧说法，那不代表现在的立场。

这些模块是公开、有文档、能逐行看的 Python API，不包含任何绕过鉴权的隐蔽入口。

## 许可证

本项目依据 AGPL-3.0-or-later 协议开源，与上游一致。详见 LICENSE 文件。

本项目为独立维护分支，与上游作者无从属关系。
