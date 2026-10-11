# Hook 时序影响面排查与 `hook_timing_mode` 规划

> 任务：**T8-01R**（2026-10-10）。本轮**只排查与规划，不写 core 代码、不动台账、不部署**；
> 开关的实施并入 **T8-07**（runner 拆分重写）。
> 关联：`inventory.md` §4 P11 的 **β 组**、`project_rules.md` §5（合并红线）。

## 1. 结论摘要

1. **本机 17 个插件：硬风险 0 项**，受益 2 个（`content_safety_guard`、`astrbot_enhance_mode`），
   需观察 1 个（`livingmemory` 入库文本可能早于审计）。
2. **官方生态抽样**：71 个候选仓库（47 个已上架）中，受益 7 / 有风险 3（+2 待复核）/ 无影响 4。
   推测 2443 个插件里真正受损的 **≤20–40 个**，集中在「钩子内二次发信」「读已发 message_id」两类。
3. **结论**：`enhanced`（钩子早于回复）**保持为默认**——受益侧是硬证据（上游时序下有些插件
   **根本无法正确工作**）；`legacy` 只作逃生舱。
4. **对外暴露只读查询**（铁律 1），插件可自检当前模式并自行降级或提示用户，避免静默故障。
5. **legacy 范围已定稿（方案乙）**：只延后 **1130 / 1325**；**1093 保持不动**（与基线 913 逐字相同，
   动它只会偏离上游）；**977 保持 `enhanced`**（已实测为独立降级路径）。详见 4.3。

## 2. β 时序事实（含一处口径更正）

`_complete_with_assistant_response`（`astrbot/core/agent/runners/tool_loop_agent_runner.py:201-307`）
内部结构：**285-287** 置 `final_llm_resp` / 状态 DONE / 统计 → **289-301** 追加 assistant 消息 →
**303-306** `await self.agent_hooks.on_agent_done(...)` → **307** `_resolve_unconsumed_follow_ups()`。
派发链：`astr_agent_hooks.py:23` → `OnLLMResponseEvent`(31-35) → `OnAgentDoneEvent`(36-41)。

| 调用点 | 路径 | 基线对应 | 相对 yield 的位置 | fork 属性 |
|---|---|---|---|---|
| **977** | 图片不可用早退 | ——（基线无） | yield **之前** | **fork 新增** |
| **1093** | 普通无工具完成 | 基线 **913** | 两版都在 yield **之前**，相对位置未变 | 未变 |
| **1130** | skills_like 重查询兜底 | 基线 **972**（在 yield **之后**） | **被上移到 yield 之前** | **β 根因** |
| **1325** | 工具连败最终回复 | ——（基线无 `final_response`） | yield **之前** | **fork 新增** |

**β 根因是 1130，不是 1093**（此前文档未精确到行号，此处更正）：

- 基线：`git show baseline/v4.28.2:...runner.py | sed -n '950,975p'`
  → `await self._complete_with_assistant_response(llm_resp)` 位于 llm_result yield **之后**（旧行 972）。
- 维护版 1125-1131：同一调用被移到 `yield AgentResponse(type="llm_result", ...)` **之前**（1130）。
- 1093 与基线 913 **逐字相同**（`if not llm_resp.tools_call_name:` 后立即调用），非根因。

### 2.1 977 独立性实测（用户要求校验）

`tool_loop_agent_runner.py:971` 的守卫是 `if getattr(self.req, "image_input_unavailable", False):`，
位于 `_step()` **开头**、工具调用之前，构造固定文本「当前看不到图片，请重新发送。」后
`return`（989）。置位点只有：

- `pipeline/.../image_input.py:130`（图片处理阶段判定不可用）
- `astr_main_agent.py:844`、`provider/sources/openai_source.py:191`、`provider/entities.py:324`

**结论：用户的判断成立** —— 977 是一条**独立的降级/错误早退路径**，正常对话不会进入；
且它是 fork 新增（上游根本没有这条统一降级回复），所以它在 `legacy` 下保持 `enhanced`
**不会造成任何与上游的兼容性差异**，还能让审计更早介入。**977 保留 enhanced。**

## 3. 影响面排查

### 3.1 L1 本机实例（17 个插件）

插件根：`…/instances/83ca721d-…/core/data/plugins`；私有仓 `D:/asbot_extras` 与实例副本逐字节一致。

| 判定 | 插件 | 依据 |
|---|---|---|
| **受益** | `content_safety_guard` | `main.py:1174` on_llm_response(1000) 审查+改写、`1356-1388` on_agent_done 覆写 `messages[-1]`；只依赖「消息已追加、尚未持久化」，**不依赖已发送** |
| **受益** | `astrbot_enhance_mode` | `main.py:3263` on_llm_response(2000) 改写 + `stop_event()`(3374)、`3162`(1500) 价值判定、`3376`(500) 二次复核——更早丢弃/改写优于更晚 |
| 需观察 | `livingmemory` | `main.py:345` 反射入库读 `resp.completion_text`；若优先级早于审计，可能存到**未审计**文本 |
| 无影响 | `debounce`(458)、`splitter`(198/202)、`AtTool`(235)、`meme_manager`(344/348/352)、`self_learning`(459)、`image_studio`(641)、`proactive_chat`（自有派发）、其余 7 个命令型插件 | 挂在 decorating / after_message_sent 阶段，或根本不接 core 的 `on_agent_done` |
| **有风险** | —— | **0 项**：本机无任何插件满足判据 (a)(b)(c) |

### 3.2 L2 官方插件生态

- **权威索引**：`https://api.soulter.top/astrbot/plugins`，实测 **2443** 条（约 2.0 MB）。
  `AstrBotDevs/AstrBot_Plugins_Collection`（`plugins.json`，1329 条）README 已标记 **DEPRECATED**，属过时源；
  `Astrbot_Plugins_Market` 只是 Vue 前端，无数据文件。
- **检索**（GitHub code search，`language:Python`，未遇限流；每查询取首页 40 条，属**样本非全量**）：
  `on_agent_done`+`AstrMessageEvent` 72；`OnLLMResponseEvent` 87；`on_llm_response`+`AstrMessageEvent` 333；
  `on_decorating_result`+`AstrMessageEvent` 280。去重得 71 个仓库，与索引交叉后 **47 个确认已上架**。

| 判定 | 数量 | 代表（证据） |
|---|---|---|
| **受益** | 7 | `astrbot_plugin_sylanne`（docstring：在 save **之前** scrub）、`astrbook`（修复正文）、`suanle_bushuo`（先 `_clear_llm_response` 再静默，必须早于发送）、`regex_filter`、`error_pro`、`memora`（注释实证：非流式结果在 `OnLLMResponseEvent` **之后**才建结果链并发送 → 插件可在发送前替换）、`outputpro` |
| **有风险** | 3（+2 待复核） | `better_send_message_to_user`（`priority=1000` 钩子内**再发一条消息**并假定排在回复之后 → 顺序语义被改写，**最高风险**）；`private_companion` / `image_companion`（注释「on_agent_done has not run yet, so there is **no official assistant message to stage**」）；待人工看代码：`iris_chat_memory`（钩子内 delete_conversation）、`recall_cancel`（疑依赖 message_id） |
| 无影响 | 4（推测） | `359_debug`、`llm_monitor`、`token_scope`、`cost_control`——只做计数/埋点 |

**规模估计（推测，非实测）**：2443 中直接用这 4 个 hook 的约 **2%–6%（50–150）**，真正受损 **≤20–40**。
不确定性：code search 首页偏置（相关性高的更易进前 40，有风险类被系统性高估）、不索引私有/新仓、
经兼容层注册的钩子搜不到、1/3 样本未上架。

### 3.3 L3 判据（什么算「依赖消息已发送」）

- **(a)** 钩子内再次发消息，并假定顺序在原回复**之后**；
- **(b)** 读取/依赖已发送状态、message_id 或 `event` 上表示「已发送」的字段；
- **(c)** 依赖 `llm_result` / `OnLLMResponseEvent` 先到达再做计数、统计、落库；
- **(d)** 需要在回复发出**之前**改写/拦截/丢弃 → 这类是 **受益方**（本项目要支持的正是这类）。

## 4. `hook_timing_mode` 接入点规划

### 4.1 配置项

`astrbot/core/config/agent_runner.py:9` 的 `AGENT_RUNNER_CONFIG_DEFAULTS["local"]["misc"]`
（现为 `max_steps` / `tool_schema_mode` / `tool_call_timeout` / `sanitize_context_by_modalities`）
新增 **`hook_timing_mode`**，默认 **`enhanced`**，可选 **`legacy`**；
同步 `astrbot/core/config/default.py` 的 misc schema。

### 4.2 传参链（照 `tool_schema_mode` 的既有先例）

`MainAgentBuildConfig`（`astr_main_agent.py:161-220`）→ `build_main_agent`(1655) →
`reset`(1861-1891) → runner `reset`（`tool_loop_agent_runner.py:310-336`，已有
`tool_schema_mode: str | None = "full"` 同款 kwarg）。
`astrbot/core/star/context.py:292` 的 `ToolLoopAgentRunner()` 无参构造只转发 `other_kwargs`，**不必改**。

### 4.3 改动点（逐点后移方案）

> ### ✅ 决策（2026-10-10，T8-07 定稿）：**只延后 1130**
>
> **legacy 的定义**：凡**上游有对照的路径**逐点等于上游；**fork 独有的路径**保留效率优化。
> 优先级：**原版插件 100% 兼容 > fork 效率优化透传**；一旦冲突，无条件退守原版行为。

| 调用点 | 上游有对照？ | legacy 下的处置 | 理由 |
|---|---|---|---|
| **1093** | 有（= 基线 913，逐字相同） | **不动** | 本来就等于上游；延后反而比上游更晚 |
| **1130** | 有（基线 **972** 在 yield 之后） | **延后到 yield 之后** | **β 根因**，唯一真正偏离上游的点，兼容性的核心 |
| **977** | **无**（fork 新增的图片降级早退） | **保持 `enhanced`** | 上游根本没有这条路径，原版插件在上游永远走不到；延后换不来兼容收益，只会丢掉优化 |
| **1325** | **无**（基线无 `final_response`，fork 的末轮补生成） | **保持 `enhanced`** | 同上；属 fork 效率优化，按「非冲突路径尽量透传」保留 |

实施时**只在 1130 一处**加 `if legacy:` 分支，把 `_complete_with_assistant_response`
移到该路径 yield 之后（照基线 972 的位置）；977 / 1093 / 1325 **一行不动**。
`_finalize_aborted_step`(1309) 独立调用 `on_agent_done`，本轮不处理。

**开关本身**（T8-07 落地）：配置项 `agent_runner.config.misc.hook_timing_mode`
（默认 `enhanced`，可选 `legacy`），沿 `tool_schema_mode` 的既有链路传到 runner；
对外经 `astrbot.api.runtime.hook_timing_mode()` 只读暴露。

### 4.4 api 暴露（铁律 1：新能力只落 `astrbot/api/**`）

新增**只读**查询「当前 hook 时序模式」的公开符号（建议落在 `astrbot/api/runtime`，与既有运行时工具同模块）：

- 必须有：模块 docstring、显式 `__all__`、逐符号 docstring、常量 `#:` 注释（§9 文档门槛）
- 同步 `docs/maintained/api-contract.md`
- **降级语义**：core 缺席时返回 `enhanced`（与 fork 默认一致），不得抛异常
- 测试：`tests/maintained/test_api_doc_gate.py`、`test_api_surface.py`（含 `EXPECTED_ALL`）必须全绿
- 插件用法：自检当前模式，遇 `legacy` 时自行降级或提示用户，避免静默故障

### 4.5 测试复用（成本低）

`tests/test_tool_loop_agent_runner.py:1751` 走的正是 **1130** 路径：fixtures `runner`(506) /
`mock_hooks`(400-414)；1791-1799 `reset(tool_schema_mode="skills_like")`；1804-1812 包裹
`runner.step` 记录 `hooks_at_emission`；断言 1833 `[False, False] + ([True, True] if streaming)`
**就是 legacy 语义**。实施时给该 reset 加 `hook_timing_mode` 即可双模式覆盖；
`910` 的 `agent_done_called` 可作粗粒度回归。

### 4.6 cron 与子代理（background）唤醒路径的透传（T8-11）

> 2026-10-11 定稿并实施。

`cron/manager.py` 的 `_woke_main_agent` 与 `astr_agent_tool_exec.py` 的
`_wake_main_agent_for_background_result` **不走 pipeline 的 `agent_sub_stages/internal.py`**，
而是各自就地构造 `MainAgentBuildConfig`。T8-07 之后它们仍只从 misc 读
`max_steps` / `tool_call_timeout`，于是 `hook_timing_mode`（连 `tool_schema_mode` 一起）
在这两个场景**恒为数据类默认值** —— 即使用户把模式配成 `legacy`，
**定时任务与后台任务唤醒的 agent 也收不到**，legacy 的逃生舱作用在这两类场景失效。

处置：两处一并读取 misc 的 `tool_schema_mode` 与 `hook_timing_mode`，
经 `normalize_hook_timing_mode` 归一化（非法值回落 `enhanced`）后传入 `MainAgentBuildConfig`。

| 字段 | 变更前 | 变更后 | 默认配置下的行为变化 |
|---|---|---|---|
| `tool_schema_mode` | 恒为数据类默认 `"full"` | 读 `misc.tool_schema_mode` | **无**（配置默认即 `"full"`） |
| `hook_timing_mode` | 恒为数据类默认 `"enhanced"` | 读 `misc.hook_timing_mode` | **无**（配置默认即 `"enhanced"`） |

⇒ 两者都是「配置驱动、默认值不变」，符合兼容边界的**加法规则**：
只有显式改配置的用户才会看到差异，而那正是他想要的语义。

**不调用 `set_hook_timing_mode`**：该全局量由 pipeline 初始化（`internal.py:104`）记录，
语义是「最近一次主对话 agent 构建的时序模式」，供
`astrbot.api.runtime.hook_timing_mode()` 对外只读查询。定时任务 / 后台任务与聊天会话
读的是**同一份配置**，值必然相同；让后台路径回写全局只会引入无谓的跨场景副作用。

## 5. 已知不兼容 / 需观察名单与后续待办

| 项 | 处置 |
|---|---|
| `better_send_message_to_user`、`private_companion`、`image_companion` | 官方生态**有风险**；`legacy` 即逃生舱。列入后续「兼容名单」文档（T7-90 解除后再对外） |
| `iris_chat_memory`、`recall_cancel` | 待人工看代码后再定级 |
| `livingmemory`（本机） | 登记为待办：确认其入库优先级是否早于审计，必要时加审计后校正或调低优先级 |

**本轮不做**：改 core、动台账、部署重启、任何 T7-90 相关对外材料。
