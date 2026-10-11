# 存量补丁清单与分级结论（阶段 2 产出）

> 来源：归档仓 `maintenance_repos/astrbot_local` 的 `baseline_source/core` ↔ `maintained_source/core` 实测 diff。
> 实测总计：**26 文件，+1639 / -91**（4 新增 + 22 修改），与交接包一致。

## 0. 先说结论

| 分级 | 文件数 | 处置 |
|---|---|---|
| ✅ **必须留在 core**（无钩子可替代） | 17 | 保留补丁，按 §4 重构后进入主干 |
| 🟡 **重写后保留**（职责错位/硬编码） | 4 | 语义保留，实现重写为数据驱动 |
| ⚪ **可上移 `astrbot/api/**`**（纯判定/契约） | 2 | 判定逻辑开放给插件，避免重复实现 |
| 🔵 **非 core 补丁**（dashboard 前端，独立改线） | 4 | 保留但重分类，不参与 core 论证 |

**一句话**：这 1639 行不是"AI 产的乱码"，而是**三条真实产品语义**的实现——① 同账号连发消息合并与在途取消；② 交付保障（要代码必须给代码 / 工具失败熔断 / 图片不可用不幻觉）；③ 维护保护与执行授权。架构问题是**耦合方向反了**：core 反向硬依赖具体插件名与工具名。

## 1. 交接包需要修正的 4 处

| # | 交接包说法 | 实测事实 |
|---|---|---|
| 1 | `platform/sources/aiocqhttp/aiocqhttp_message_event.py` +22 =「QQ 图片本地化」 | **不准确**。该 22 行全是「直报回合发送闸门」（`is_current` / `mark_sent`）。真正的图片 URL 归集在 `direct_turns.prepare()`，且**只保存 URL 字符串，不做 URL→本地文件下载** |
| 2 | 补丁路径写作 `astrbot/utils/direct_turns.py` 等 | 4.28.2 真实布局是 `astrbot/core/utils/direct_turns.py`（多一层 `core/`） |
| 3 | `dashboard/src/services/plugin_service.py` | 实际路径 `astrbot/dashboard/services/plugin_service.py`（属后端，不是前端） |
| 4 | 「`maintenance.py` 拦不住启动器」 | **属实**，但更准确：它只拦 **进程内** 4 条更新路径（`PluginManager.update_plugin` / `_install_plugin_from_directory` / `_PluginUpdater.update` / Dashboard 的 `update_plugin`+`update_all_plugins`）。`uninstall_plugin` **未挂闸门**，存在「先卸载再安装」绕过；且 `registry` 文件缺失时 **fail-open** 静默放行 |
| 5 | 补丁清单未点明两个"心脏" | `direct_turns.py`(316) 与 `code_delivery_policy.py`(217) 是本次补丁的底座与判定层；不读它们无法理解任何一条小改动 |

## 2. 全景依赖图

```
                       ┌──────────────────────────────────────────┐
                       │  direct_turns.py  【底座】                │
                       │  DirectTurnCoordinator 单例               │
                       │  observe/collect/prepare/finish           │
                       │  is_current / mark_sent                   │
                       │  工具结果复用 begin/record/get/release     │
                       └───────┬──────────────────────┬────────────┘
       挂载点（7 处 core）      │                      │ 消费
   ┌───────────────────────────┴──────────┐           │
   │ scheduler.py      observe/finish     │           │
   │ process_stage/stage.py   collect     │           │
   │ .../internal.py          prepare     │           │
   │ .../follow_up.py         proactive   │           │
   │ pipeline/respond/stage.py 出站门禁    │           │
   │ pipeline/context_utils.py 钩子门禁    │           │
   │ aiocqhttp_message_event.py 平台门禁   │           │
   └──────────────────────────────────────┘           │
                                                      ▼
   ┌────────────────────────────┐        ┌─────────────────────────────┐
   │ code_delivery_policy.py    │        │ tool_loop_agent_runner.py   │
   │ 【判定层】                  │───────▶│ 【执行中枢】                 │
   │ execution_denial           │  4 符号 │ 轮次门禁 / 工具去重          │
   │ code_task_spec             │        │ REPEATED_TOOL_FAILURE_LIMIT │
   │ has_code_delivery          │        │ 交付修复 / 图片短路          │
   │ apply_execution_policy     │        │ _finish_proactive_request   │
   └──────────┬─────────────────┘        └──────────┬──────────────────┘
              │ 消费                                 │ 消费
   ┌──────────┴───────────┐              ┌───────────┴──────────────┐
   │ computer_tools/*     │              │ astr_agent_run_util.py    │
   │ util/shell/python     │              │ 交付闸门 _send_current     │
   └───────────────────────┘              └───────────────────────────┘

   ┌────────────────────────────┐   ┌──────────────────────────────────┐
   │ provider/entities.py       │   │ star/maintenance.py 【维护保护】   │
   │ 【数据契约】                │   │ ├─ star_manager.py (+3)           │
   │ IMAGE_INPUT_UNAVAILABLE_*  │   │ ├─ updater.py (+2)                │
   └──┬───────┬──────────┬──────┘   │ └─ dashboard/plugin_service.py(+17)│
      │       │          │          └──────────────────────────────────┘
      ▼       ▼          ▼
  astr_main  image_   openai_source.py
  _agent.py  input.py  (+97 容错)
   (+152)
```

## 3. 逐文件分级表（26 条）

图例：**A**=新增 / **M**=修改；判据「能否不改 core 在插件层实现」。

### 3.1 必须留在 core（✅ 17）

| # | 文件（`astrbot/core/` 起） | A/M | 行数 | 功能目标 | 为什么必须留 core |
|---|---|---|---|---|---|
| 1 | `utils/direct_turns.py` | A | +316 | 同账号连发消息聚合成一轮 + 取代旧轮 + 在途取消 + 工具结果复用 | 需在消息进 pipeline **前**扣留（可阻塞钩子不存在）；需持 runner 句柄调 `request_stop` |
| 2 | `agent/runners/tool_loop_agent_runner.py` | M | +443/-20 | 轮次门禁 / 同参工具只跑一次 / 失败熔断 / 交付修复 / 图片短路 | 位于步进循环内部；插件无「执行前替换工具返回值」「最终响应前改写」钩子 |
| 3 | `astr_agent_run_util.py` | M | +62/-8 | 交付闸门：被取代轮次不得发中间消息/最终结果 | per-step 与 chunk 交付边界，无钩子覆盖 |
| 4 | `pipeline/process_stage/stage.py` | M | +4 | `await coordinator.collect()` 静默期等待（合并实际发生点） | 必须在 agent 子阶段前，且早于 `on_llm_request` |
| 5 | `pipeline/scheduler.py` | M | +3 | `observe` / `finish` 生命周期挂载 | pipeline 唯一入口，无法外移 |
| 6 | `pipeline/process_stage/method/agent_sub_stages/internal.py` | M | +47 | 合并文本/图片注入 `req`；三处失活短路 | 必须位于 session lock 与 `build_main_agent` 之间 |
| 7 | `pipeline/respond/stage.py` | M | +16 | 出站最后门禁（流式 + 3 条非流式路径） | 出站必经点 |
| 8 | `pipeline/context_utils.py` | M | +16 | 失活回合不触发 `OnLLMResponse`/`OnDecoratingResult` 钩子；**修复 `CancelledError` 被吞** | 影响全部插件生态的钩子调度；`CancelledError` 是独立 bug fix |
| 9 | `platform/sources/aiocqhttp/aiocqhttp_message_event.py` | M | +22 | 平台层最后一道发送门禁（防插件直接 `event.send`） | 平台适配器内部 |
| 10 | `provider/sources/openai_source.py` | M | +97 | 图片不可用时的确定性回退（摘工具 + 注入声明 + 固定文案）；流式缓冲重放 | provider 传输层错误恢复，无 `on_provider_fallback` 钩子 |
| 11 | `provider/entities.py` | M | +30 | `IMAGE_INPUT_UNAVAILABLE_MESSAGE/NOTICE` 常量 + 双向布尔字段 | 数据契约，必须 core 侧存在 |
| 12 | `pipeline/.../agent_sub_stages/image_input.py` | M | +30 | 视觉证据存在性判定 → `req.image_input_unavailable` | 低成本纯判定；建议同时开放 helper |
| 13 | `astr_main_agent.py`（图片降级 + 策略挂载部分） | M | +152/-27 | `_ensure_img_caption` 降级；末尾 `apply_execution_policy` | 降级语义属 core 职责 |
| 14 | `star/maintenance.py` | A | +43 | 本地维护名单拦截插件覆盖 | 纯本地运维策略，上移会污染公共 API |
| 15 | `star/star_manager.py` | M | +3 | 更新/目录安装前断言 | 挂载点只能在 `PluginManager` 内 |
| 16 | `star/updater.py` | M | +2 | 下载前最后一道断言 | 防绕过 `PluginManager` 直调 |
| 17 | `astrbot/dashboard/services/plugin_service.py` | M | +17 | 单个更新报错、批量更新「跳过而非失败」；顺带修正 `sync_skills` 触发条件 bug | 与 maintenance 强绑定 |

### 3.2 重写后保留（🟡 4）

| # | 位置 | 问题 | 重写方向 |
|---|---|---|---|
| 18 | `astr_main_agent._is_lightweight_proactive_request` + `_apply_lightweight_proactive_tools` | **core 硬编码插件目录名 + 反向回调插件方法**；29 个工具名硬编码（含大量第三方工具） | 白名单外置为配置；插件通过公开钩子声明「本次请求的可用工具」；去掉目录名硬匹配 |
| 19 | `code_delivery_policy.execution_denial` + `EXECUTION_TOOL_NAMES` | 硬编码 4 个工具名字符串；中文祈使句正则启发式，双向误判；`allowed=True` 时仍无条件注入 system prompt | 工具自身声明 `requires_execution_authorization`；prompt 仅在检测到代码意图时注入且可配置 |
| 20 | `tool_loop_agent_runner._finish_proactive_request` | 遍历 `star_registry` 按目录名找插件实例（架构倒挂） | 改为事件钩子（如 `OnAgentDoneEvent` + extra token），core 不认识任何插件名 |
| 21 | `pipeline/process_stage/follow_up.py` 的 `try_capture_follow_up` | 与 `direct_turns.observe` 的 `other` 判定**重复实现**；`self_id` 缺失时把所有 @ 当"@别人"误丢 | 复用 `direct_turns` 暴露的判定函数；补齐 `self_id` 兜底语义 |

### 3.3 可上移 `astrbot/api/**`（⚪ 2）

| # | 内容 | 上移理由 |
|---|---|---|
| 22 | `IMAGE_INPUT_UNAVAILABLE_MESSAGE` / `IMAGE_INPUT_UNAVAILABLE_NOTICE` 常量 | 已被 core 三处 + 插件一处共同消费，是事实公共契约；必须进 `astrbot.api.provider` 稳定面，插件才能改软依赖 |
| 23 | `code_task_spec` / `has_code_delivery` / `CODE_DELIVERY_FAILURE`（纯函数） | 纯函数、无副作用，插件可复用；同时抽 `IMAGE_CAPTION_MARKER` 常量消除 5 处 `"<image_caption>"` 硬编码 |

### 3.4 非 core 补丁 · 前端独立改线（🔵 4）

| # | 文件 | A/M | 性质 | 说明 |
|---|---|---|---|---|
| 24 | `dashboard/src/utils/messageControlDisplay.js` | A | 全新 | 把 `<quote>` / `<mention>` 控制标签渲染为可读文本，保护代码块不被误改。服务对象是 **Satori 适配器**产出的标签，**与本次 core 补丁无呼应** |
| 25 | `dashboard/src/components/chat/ThreadedMarkdownMessagePart.vue` | M | +5 | 同上 util 的接入点（Thread 面板） |
| 26 | `dashboard/src/components/chat/message_list_comps/MarkdownMessagePart.vue` | M | +4 | 同上 util 的接入点（主列表） |
| 27 | `dashboard/src/assets/mdi-subset/materialdesignicons-subset.css` | M | +14 | **实为删减**（272→269 图标），自动生成产物刷新（`pnpm run subset-icons`）。标记为「+14」具误导性 |

> 25/26 存在性能隐患：`messageControlDisplay` 在 computed 内每条消息每次重算（含 `markitdown-it` 全量 parse），流式渲染时对每条 token 都会重跑，**无 memo**。

## 4. 跨文件共性问题（进入阶段 3 前必须处理）

| # | 问题 | 位置 | 处置 |
|---|---|---|---|
| P1 | **插件顶层 import core 私有常量** → core 漂移即插件整体下线 | 存量插件 `main.py:28` | ① 常量上移 `astrbot.api.provider`；② 插件改 `try/except ImportError` 软依赖 |
| P2 | **core 反向硬依赖插件目录名** | 实测 **2 处**：`astr_main_agent._is_lightweight_proactive_request`、`tool_loop_agent_runner._finish_proactive_request`（早期清单写的「×2 + ×1」有误） | ✅ **已处置（T8-03）**：改为**能力契约解析** —— 只按约定的能力方法名发现插件（`is_trusted_lightweight_proactive` / `finish_proactive_request`），core 零插件名、行为逐点等价、无需改插件。契约与守卫见 `docs/maintained/plugin-capability-lookup.md` |
| P3 | **工具名硬编码白名单** | `code_delivery_policy.EXECUTION_TOOL_NAMES`（4 个，全 core 自带）、`astr_main_agent._LIGHTWEIGHT_PROACTIVE_TOOL_NAMES`（29 个，**多为第三方插件工具**） | ✅ **已处置（T8-04）**：分两半 —— 执行类**纯自声明**；轻量主动类**自声明 + 配置名单并集**（第三方插件不会来声明，纯自声明会让主动回复静默失去工具）。声明字段 `FunctionTool.is_execution_tool` / `is_lightweight_proactive_safe`（照 `is_background_task` 先例，默认关闭）；配置兜底 `agent_runner.config.misc.lightweight_proactive_tools`（默认 29 个）。详见 `docs/maintained/tool-capability-declaration.md` |
| P4 | **隐式字符串协议** | `"<image_caption>"` 在 5 处硬编码；`"<quote>"`/`"<mention>"` 亦无共享常量 | 抽共享常量 |
| P5 | **跨模块写私有属性** | `astr_agent_run_util` 写 `agent_runner._proactive_delivery_deferred` | 提升为正式字段 + 公开方法 |
| P6 | 权限双模型并存 | `check_admin_permission` 与 `check_execution_permission` 并存（`fs.py` 仍只用前者） | ✅ **已处置（T8-05）**：两套判定合到单一入口 `check_tool_permission(context, operation_name, level)`（`ToolPermissionLevel.IDENTITY` / `EXECUTION`），**判定强度逐点保持现状、行为零变化**；fork 私有的 `check_execution_permission` 已删除。**未合并成 AND** —— 那会把 `execution_denial` 的已知误判扩散到原本不看意图的 11 个调点（违反兼容立场）。上游符号 `check_admin_permission` 保留为身份级转发器（它在 `computer_tools.__all__` 导出，且上游测试以其名做 monkeypatch）。详见 `docs/maintained/tool-permission-entry.md` |
| P7 | 静默丢弃不可观测 | `respond/stage.py`、`aiocqhttp_message_event.py`、`context_utils.py` 门禁均无日志 | 补 debug 日志与丢弃计数 |
| P8 | 魔法数字未提取 | `timeout=30`、`16000`、`15s`、图片上限 2、`quiet_sec=4`、`max_wait_sec=15` | 提取常量或配置项 |
| P9 | `maintenance` fail-open | registry 文件缺失**静默**放行（无日志）；`uninstall_plugin` / `uninstall_failed_plugin` **无闸门** | ✅ **已处置（T8-06）**：缺失 → **明确 `logger.warning`（含路径与原因）后放行**（不改 fail-closed：该 registry 是本 fork 私有机制，公开后多数用户没有它，fail-closed 会锁死纯净环境）；损坏 → 仍 fail-closed；卸载两入口补闸门并留 `force=False` 逃生口（`force` **暂不在面板暴露**）。详见 `docs/maintained/maintenance-gate.md` |
| P10 | 手写正则做安全判定 | `SAFETY_REFUSAL_PATTERN`、`execution_denial` 中文祈使句 | 明确误判容限并补测试（阶段 3 必做） |
| **P11** | **维护版 core 打破上游 17 项测试预期**（阶段 7 新发现） | 见下方对照表 | **登记不改**：属补丁质量证据，须在"插件重写"批次统一处理；任何 core 打磨都必须以"不新增失败"为验收 |

### P11 证据（2026-10-09 对照实验）

用 `git worktree` 检出**纯基线** `baseline/v4.28.2`（`3c7adafa`）与维护版工作树，
在**同一测试环境**下跑同一批上游测试：

| 上游测试文件 | 纯基线 | 维护版 | 差异 |
|---|---|---|---|
| `tests/unit/test_astr_main_agent.py` | **134 passed** | 9 failed / 125 passed | **9 项回归** |
| `tests/test_tool_loop_agent_runner.py` | **53 passed** | 8 failed / 45 passed | **8 项回归** |
| `tests/test_process_stage_images.py` | 125 passed | 125 passed | 无 |

失败集中在 `test_skills_like_requery_reply_reaches_stream_bridge_once`
（断言 `hooks_at_emission` 期望 `[False, False, True, True]`，实测 `[True, True, True, True]`），
指向 `tool_loop_agent_runner.py` 中交付/钩子时序被补丁改变。

**结论与处置**：

1. 这是**补丁自身的既存回归**，与阶段 7 的 P4/P5/P7/P8 打磨无关（打磨前后均为 17 项失败）。
2. 因此阶段 7 的 core 打磨验收标准为「**不新增失败**（17 → 17）」，而非"上游测试全绿"。
3. 与 `inventory.md` 对 `tool_loop_agent_runner.py` 的判定一致（该文件被列为需**拆分重写**的 🟡 项）；
   真正的修复应在"插件/补丁重写"批次统一做，避免在零测试保护下动交付时序。
4. **副作用提示**：`tests/test_process_stage_images.py` 全绿，说明图片降级链路的上游预期未被破坏。

#### P11 逐类归因（2026-10-09 补充）

三类失败，全部是**行为有意偏离**，非崩溃：

| 组 | 数量 | 断言在测什么 | 维护版做了什么 | 影响 |
|---|---|---|---|---|
| **α 执行工具授权收紧** | 9（`test_proactive_agent_respects_runtime_and_safety_settings` ×8 + `test_persona_empty_tools_keeps_local_runtime_builtin_tools` ×1） | `runtime == "local"` 时工具集应含 `astrbot_execute_python` / `astrbot_execute_shell` | `apply_execution_policy`（`astr_main_agent.py:1857`，**无任何条件、每次请求都调用**）在 `execution_denial` 非空时过滤掉 `EXECUTION_TOOL_NAMES`（python/ipython/shell/shell_session） | **有真实影响且对全部对话生效**：非管理员**永远**拿不到执行工具；管理员也必须在**当前消息里明确要求运行/执行**（写代码、解释、引言都不算授权）。属**有意的安全加固**（防"引用的代码被当授权执行"），方向是**更严格** |
| **β hook 发射时序** | 8（`test_skills_like_requery_reply_reaches_stream_bridge_once`） | 前两次发射时 hook 标记应为 `False`（"保持既有 `llm_result` 顺序，只有新增的流式增量跟在 hook 之后"） | 维护版里 hook 标记**更早**被置 True（实测四个发射点全为 `True`） | 🟢 **本项目的核心架构优化，属设计预期** —— **保留现状，坚决不改回上游；严禁上游合并时覆盖**（见下方 β 章节与 `project_rules.md` §5） |
| **γ 对照** | **0**（`test_process_stage_images.py` **125 全绿**） | 图片不可用降级链路的既有预期 | 未改动语义 | 无需处理；此组全绿**正是 P4 零行为变化的证据** |

**净评估**：边界清晰（集中在 `astr_main_agent.py` 与 `tool_loop_agent_runner.py` 两个文件），无崩溃、无数据损坏。
- **α（9 项）**：执行工具授权收紧 —— 设计使然的预期失败，方向更严格，**保留**。
- **β（8 项）**：hook 完成时序 —— 🟢 **核心架构优化，设计预期，坚决保留、严禁上游覆盖**。
- **γ（0 项）**：对照组，全绿。

**未重开主动回复前，α 中与主动场景相关的部分不会生效；但 α 的"执行工具收紧"对所有对话生效。**

#### β 根因更正（2026-10-09 深夜复核，推翻初判）

**初判（错）**：以为是补丁把 `on_agent_done` 调用挪了位置。

**实测更正**：承载该钩子的 `ToolLoopAgentRunner._complete_with_assistant_response()`
在**基线与维护版中逐行相同**（顺序均为：追加 assistant 消息 → 调 `on_agent_done` → `_resolve_unconsumed_follow_ups()`）。
所以**钩子本身没有被挪位**；真正变化的是**"这一轮何时被判定为完成"**——

> **精确行号（2026-10-10 T8-01R 补）**：β 根因是 **`tool_loop_agent_runner.py:1130`**
> （skills_like 重查询无工具调用的兜底路径）——基线同逻辑的调用在 **972**，位于 llm_result
> yield **之后**；维护版把它移到了 yield **之前**。另外 3 处调用点：
> **977**（图片不可用早退，fork 新增）、**1093**（= 基线 913，相对位置未变）、
> **1325**（工具连败最终回复，fork 新增）。详见 `docs/maintained/hook-timing-impact.md` §2。
补丁新增的代码交付修复 / 末轮补生成逻辑（该方法上方的 `language` / `outcome` 记录与修复路径）
使 `_complete_with_assistant_response` 在更早的一步被调用，于是当最终两条 `llm_result`
经过 `step()` 时，钩子标记已经是 `True`。

**谁受影响**：`on_agent_done` → `MainAgentHooks.on_agent_done` 会派发
`OnLLMResponseEvent` 与 `OnAgentDoneEvent`。
**实例中的 `astrbot_plugin_content_safety_guard` 正挂在 `@filter.on_agent_done(priority=1000)` 上**
（处理函数 docstring：「Replace the runner's pre-audit message **before core history persists it**」）。

**影响判定**：guard 的关键依赖是「钩子在**追加 assistant 消息之后、core 写历史之前**触发」——
该位置**未被破坏**。变化的是「钩子 vs 回复被发出」的先后：维护版钩子更早，
对 guard 这类「拦截 / 清空回复」的逻辑**更早触发反而更安全**。

**⇒ 处置决定（2026-10-10 用户定调，最终）**

> ### 🟢 β 是**本项目的核心架构优化**，属**设计预期**，**保留现状、坚决不改回上游**；
> ### **严禁上游合并时覆盖**（`project_rules.md` §5 已列为合并红线）。

理由：官方为了让 hook 时序兼容大众既有用法而做的妥协（"回复先出、钩子后到"），
正是本项目要优化的痛点——把"这一轮何时算完成"提前，才能让**拟人化干预**
（内容审计、回复替换、丢弃被拒回复）在**回复发出之前**拿到控制权。
对齐上游测试 = 放弃这项能力，**不做**。

**落地要求**：
1. 本语义受 `project_rules.md` §5「合并红线」保护：上游合并若在此处产生冲突，**以本 fork 为准**。
2. 重写/重构该文件时，**该时序优化必须保留**（`_complete_with_assistant_response` 的调用时机）。
3. 建议（非必须）为「guard 丢弃被拒回复」补一条针对性测试，把这项优化**钉成可回归的不变量**，
   以免将来重构时无意改回上游时序。

#### P11 机械定型（2026-10-10，T8-01）

上游测试文件**一字不改**（零冲突原则 §3）。改用**两个新增文件**把 17 项标记为 `xfail(strict=True)`：
仓库根 `conftest.py`（`pytest_collection_modifyitems` 打标）+ `maintained/p11_deviations.py`（注册表，
单一真相源）。逐条 nodeid 如下（2026-10-10 实测，pytest 9.1.1）：

| 组 | 文件 | 用例 | 参数组合 | 数量 |
|---|---|---|---|---|
| α | `tests/unit/test_astr_main_agent.py` | `test_proactive_agent_respects_runtime_and_safety_settings` | `True-local-cron`、`True-local-background`、`True-sandbox-cron`、`True-sandbox-background`、`False-local-cron`、`False-local-background`、`False-sandbox-cron`、`False-sandbox-background` | 8 |
| α | 同上 | `TestEnsurePersonaAndSkills::test_persona_empty_tools_keeps_local_runtime_builtin_tools` | — | 1 |
| β | `tests/test_tool_loop_agent_runner.py` | `test_skills_like_requery_reply_reaches_stream_bridge_once` | `False-True-False-False`、`False-True-False-True`、`False-True-True-True`、`False-False-False-True`、`True-True-False-False`、`True-True-False-True`、`True-True-True-True`、`True-False-False-True` | 8 |

**strict 语义（＝"测试全绿"的正式定义）**：

- `xfail(strict=True)`：用例**照常执行**；失败 → `xfailed`（绿）；**意外通过 → `XPASS(strict)` 判红**。
- 所以"这 17 项意外通过"即等于「偏离被回退 / 被上游合并覆盖」，会**立刻报警**，正合 §5 合并红线。
- 套件口径：`tests/maintained` 全绿 + 上游 `170 passed, 17 xfailed`，**没有未解释的红**。

**命中数守护**：`tests/maintained/test_p11_deviations.py` 在同一会话收集到上述两个文件时，
断言注册表命中数 `APPLIED == 17`。若上游改了用例名或参数组合导致打标静默失效，该断言会红。

**新增一条的流程**：先在本节登记理由 → 加进 `maintained/p11_deviations.py` → 跑全套验证。
**删除一条的前提**：该偏离已被有意回退，且在本节写明回退理由（否则 strict 会一直红）。

## 5. 证据来源

- diff：`git diff --no-index <归档>/baseline_source/core <归档>/maintained_source/core`
- 台账：`maintained/installed_manifest.json`（22 条 core SHA-256）
- 失败日志：`<INST>/astrbot_manual.out.log`（插件 `ImportError` 现场）
- 测试：归档仓 `tests/`（215 文件），含 `test_direct_turns.py`、`test_local_maintenance.py`、`test_image_unavailable_delivery.py` 等
