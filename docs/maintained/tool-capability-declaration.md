# 工具能力自声明（P3 处置 · T8-04）

> **目标**：core 的判定逻辑里不再有硬编码工具名白名单。
> 决策时间：2026-10-11。执行类走**纯自声明**；轻量主动类走**自声明 + 配置名单并集**。

## 1. P3 问题：两张硬编码白名单

| 白名单 | 数量 | 工具来源 | 用途 |
|---|---|---|---|
| `code_delivery_policy.EXECUTION_TOOL_NAMES` | 4 | **全是 core 自带**（`computer_tools/python.py` ×2、`shell.py` ×2） | 未获当前消息授权时，从工具集里移除这些工具 |
| `astr_main_agent._LIGHTWEIGHT_PROACTIVE_TOOL_NAMES` | 29 | **绝大多数是第三方插件工具**（`uapi_*` ×14、`enhance_*` ×3、`image_studio_*` ×2、`grok_web_search`、`recall_long_term_memory`、`get_group_message_history`、`play_song_by_name`、`query_lyrics_by_name`） | 轻量主动回复只允许这批"无副作用"工具 |

## 2. 为什么两半边处置不同

| 半边 | 处置 | 理由 |
|---|---|---|
| **A 执行类** | **纯自声明** | 4 个工具全在 core，自己声明自己，**零风险**；第三方执行类工具本来就不在名单里，改造前后一致，无回归 |
| **B 轻量主动类** | **自声明 + 配置名单并集** | 名单里大多是**第三方插件工具**，它们不会来声明；若改成纯自声明，主动回复会**静默失去**这批工具（功能回退）。用配置名单兜底 ⇒ **零行为变化**，同时用户可自行增删第三方工具 |

⇒ 兼容性立场（原版插件 100% 兼容 > fork 优化）：**B 不能为了"去硬编码"牺牲主动回复能力**。

## 3. 声明字段（`astrbot/core/agent/tool.py` 的 `FunctionTool`）

照既有先例 `is_background_task`，新增两个**默认关闭**的声明字段：

| 字段 | 语义 | 未声明时 |
|---|---|---|
| `is_execution_tool: bool = False` | 该工具会执行代码/命令，需要**当前消息**的显式授权 | 不在"未授权即移除"的集合内（与改造前一致） |
| `is_lightweight_proactive_safe: bool = False` | 该工具无主机/审核/文件/外发副作用，可进入轻量主动路径 | 不进入主动路径，**除非**名字在配置名单里 |

读取一律用 `getattr(tool, <field>, False)` 兜底：第三方可能出现鸭子类型工具对象，
显式默认值比 `AttributeError` 更安全，且与"未声明"语义一致。

## 4. 配置兜底（B 半边）

- 配置键：`agent_runner.config.misc.lightweight_proactive_tools`（字符串数组）
- 默认值常量：`astrbot/core/config/agent_runner.py` 的 `DEFAULT_LIGHTWEIGHT_PROACTIVE_TOOLS`
  （= 原 29 个名字），并登记进 `AGENT_RUNNER_CONFIG_DEFAULTS["local"]["misc"]`
- `normalize_agent_runner` 对 list 类型**原样保留用户值**（`_normalize_value` 的 list 分支），
  所以用户可在配置里增删；WebUI schema 同步在 `config/default.py`（`type: list` + `items: string`）
- 判定：`tool.is_lightweight_proactive_safe or tool.name in configured_names`

## 5. 兼容性结论

- **默认配置 + core 自带工具已声明 ⇒ 行为与改造前逐点一致**
- 第三方工具：不声明 ⇒ 与现状相同（靠名单）；用户可加配置补
- **未修改任何插件**（含 `astrbot-extras` 里的增强插件；其 `enhance_*` 工具仍靠名单生效）

## 6. 关于六铁律 1（新增能力只落 `astrbot/api/**`）

这两个字段是 `FunctionTool` 的**数据契约**（构造工具时传参），**不是新的能力入口**，
且必须长在 `FunctionTool` 上 core 才读得到；故**不在 api 面新增符号**，
避免公开面无谓膨胀（`EXPECTED_ALL` 不变）。
若将来要给插件更正式的声明入口（如 `astrbot.api.tools.declare(...)`），再单独走 api。

## 7. 测试载体

`tests/maintained/test_tool_capability_declaration.py`：

- 执行类：声明的工具在未授权时被移除、未声明的保留、对象缺字段时按未声明处理；
- 轻量主动：声明者入选、配置名单者入选、两者皆非则淘汰、默认名单读得到；
- 守卫：`code_delivery_policy` 与 `astr_main_agent` **不再暴露**旧的白名单常量
  （防止有人把硬编码名单加回来）。
