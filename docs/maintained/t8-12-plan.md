# T8-12 拆分重写 · 执行计划（定稿）

> 定稿时间：2026-10-13。负责人拍板：① 保守粒度 ② 扁平同级模块 ③ 台账 36 → 39 ④ 文档订正纳入 Step 0'。
> **本文件是计划，不是证据。** 任何"某功能是否已存在 / 某行为是什么 / 某代码在哪一行"的主张，
> 一律以 `git log -S` / `git diff baseline/v4.28.2` / 文件实况读取为准；`docs/` 与交接文档仅作线索。

## 0. 取证原则（本轮起生效，T8-12 全程适用）

凡事实主张，必须给出 git 实况或文件实况证据：

| 主张类型 | 取证命令 |
|---|---|
| 某行为何时被引入/删除 | `git log -S"<symbol>" --oneline -- <file>` |
| 当前实现与基线的差异 | `git diff baseline/v4.28.2 -- <file>` |
| 某代码在哪一行 | 文件实况读取（`sed -n` / Read） |
| 台账是否包含某文件 | 读 `maintained/installed_manifest.json` |

不接受记忆陈述，不接受历史总结文档的转述。

## 1. 事实基线（已用 git 实况取证）

### 1.1 T8-07 **已独立交付**，不由 T8-12 承接

`hook_timing_mode` 开关是**正规配置开关**，无临时硬编码。取证：

| 环节 | 位置（实况） |
|---|---|
| 常量 / 归一化 / 全局读写 | `astrbot/core/config/agent_runner.py:7,11,15,82,256,259,275,289` |
| 默认配置 | `astrbot/core/config/default.py:4149` |
| 传参（pipeline 主路径） | `agent_sub_stages/internal.py:101-104,142` |
| 数据类字段 | `astr_main_agent.py:222`（dataclass 定义 `:163`） |
| 装配传入 | `astr_main_agent.py:1887`（`async def build_main_agent` 在 `:1661`） |
| runner 消费 | `tool_loop_agent_runner.py:39,332,412,1140` |
| cron / 子代理透传（T8-11） | `cron/manager.py:467`、`astr_agent_tool_exec.py:579` |
| **api 只读暴露** | `astrbot/api/runtime/__init__.py:104 def hook_timing_mode()`，在 `__all__`，`api-contract.md:83,85` 已登记 |

⇒ 上表 8 个文件**全部已在台账内**；T8-07 无剩余代码工作。

### 1.2 β 时序：legacy 只延后一处（澄清 1 定性，git 实况）

- `git log -S"legacy_timing" -- astrbot/core/agent/runners/tool_loop_agent_runner.py` ⇒ **唯一 commit `109c0130a`**
  （2026-10-11，commit message 明写 "977, 1093 and 1325 are untouched"）。
- 该 commit 的 diff 只动三处：import、`reset()` 参数、以及 **1130 一处**拆成 `1141 if not legacy_timing` / `1165 if legacy_timing`。
- `git diff baseline/v4.28.2 -- <runner>` 的 `@@ -1087,9 +1282,86 @@` hunk 显示：整个"工具连败末轮补生成"块
  （含现在的 **1340**）是 **+86 行纯新增**，基线侧无对应，且**无任何 `legacy_timing` 判断**。

**定性结论**：

| 调用点 | 现/旧行号 | 是否有 legacy 分支 | 性质 |
|---|---|---|---|
| 图片不可用早退 | **984** / 977 | ❌ 从未有过 | fork 新增，上游无对照 |
| 无工具调用 | **1100** / 1093 | ❌ 从未有过 | 与上游逐点相同 |
| skills_like 重查询 | **1142** / **1166** ← 旧 1130 | ✅ **唯一一处** | enhanced=提前（本 fork 优化）／legacy=延后（=上游） |
| 工具连败末轮补生成 | **1340** / 1325 | ❌ 从未有过 | fork 新增，上游无对照 |

**错误记载（Step 0' 已处置，逐条 git/grep 实况取证）**：

| 位置 | 取证结果 | 处置 |
|---|---|---|
| `docs/maintained/hook-timing-impact.md:16`「只延后 **1130 / 1325**」 | ✅ **确有错**，且是**唯一错误源** | 已订正为「只延后 1130 一处（现 1142/1166）」，并加订正注脚（提交 `977872dd9`） |
| `.workbuddy/handover.md` §2/§4「legacy 仅延后 1130/1325」 | ❌ **该记载不存在** —— `grep -n "1130\|1325\|1093\|977" .workbuddy/handover.md` **零命中**；该文件只有 §4 第 3 条「`legacy_timing` 分支（约 1140–1165）」，与实况一致 | 未改事实；只加了顶部「本文件是线索，不是证据」免责行 |
| `hook-timing-impact.md` §121/§124「1325 保持 enhanced、一行不动」 | ✅ 正确 | 未动 |

> **2026-10-13 取证澄清（本节初稿自身的一处错误）**：
> 本小节初稿（提交 `644e03b72`）称「handover 与 impact 文档**两处都错**」，
> 那是**未经取证的历史转述**。Step 0' 用 grep 实况复核后确认：
> **唯一错误源只有 `hook-timing-impact.md:16`**，`handover.md` 不含此错误记载。
> 这再次印证 §0 的取证原则 —— 计划文档与交接文档的记载同样只能作线索，不能作证据。

### 1.3 四个文件（＝ inventory §3.2 的 🟡 4 项）

| 项 | 文件 | 行数 | 剩余问题 | 与 β 的关联 |
|---|---|---|---|---|
| 18 | `astrbot/core/astr_main_agent.py` | 1905 | 硬编码已于 T8-03/T8-04 清除（能力契约 + 自声明 + 配置兜底）。**Step 3 已外迁 9 个函数**（quote 6 → #38；proactive 3 + 2 常量 → #39），**1905 → 约 1734（−9%）**。**留守 4 个**（`_append_video_attachment` / `_build_local_mode_prompt` / `_apply_local_env_tools` / `_filter_skills_for_current_config`），原因见 §3.2。**剩余技术债**：`build_main_agent`(248 行) / `collect_initial_request`(220 行) / `_ensure_persona_and_skills`(178 行) 三大函数未拆 | 间接：β 场景的入口装配方 |
| 19 | `astrbot/core/code_delivery_policy.py` | 212 | `EXECUTION_TOOL_NAMES` 已移除。**剩余两项 —— ① 正则双向误判（= **T8-10**）② `allowed=True` 时无条件注入英文 prompt。⛔ **两项 Step 2 均未处理，待 T8-10**（见 §2 Step 2 行与 §7）** | 间接但属**成因侧**：代码交付修复使完成钩子更早调用 |
| 20 | `astrbot/core/agent/runners/tool_loop_agent_runner.py` | 2039 | 目录名倒挂已由 T8-03 修掉。**剩余＝过大**：`_step()` 965-1354、`_handle_function_tools` 1392-1820 | **直接承载 β**（5 个调用点） |
| 21 | `astrbot/core/pipeline/process_stage/follow_up.py` | 264 | `185-191` 与 `direct_turns.py:116-120` **逐字重复** `other` 判定；`self_id` 处理两侧不一致（follow_up 兜成 `""` ⇒ self_id 缺失时把所有 @ 误判为"@别人"丢弃） | 相邻：`_complete_...` 末尾 308 行立刻结算 follow-up |

## 2. 执行步骤表

| 步 | 内容 | 台账 | 验收（每步停下汇报） |
|---|---|---|---|
| **0** | ✅ **已完成**（提交 `3a1bccdc8`）β 探针落地 + 5 case 基线快照 + 零保护 case 清单 | 0 | 基线 JSON 落盘、5 case 全通过 |
| **0'** | ✅ **已完成**（提交 `977872dd9`）文档订正 —— **唯一错误源 `hook-timing-impact.md:16`**；handover 只加免责行（见 §1.2 取证澄清） | 0 | 双端校验仍是 36 条 NO DRIFT（文档不在台账内，仅确认） |
| **1** | ✅ **已完成**（提交 `f1dc62650` / `2256385c4` / `652a4cfa8`）`follow_up` 去重 + `self_id` 统一（复用 `direct_turns` 判定） | 2 条哈希（**实测 2 条，与预估一致**） | 探针一致 + maintained 317 |
| **2** | ✅ **已完成**（提交 `9d892d26d` / `787700da0` / `106f115eb` / `2a39014cc`）`code_delivery_policy` 结构整理（**口径 B**：正则字符零改动 + 不许搬动 + 留在原函数原位置）。只抽 **2 个私有 helper**：`_task_text`（原 90-102）、`_drop_execution_tools`（原 186-200）。**不上提** `aliases` / `language_patterns`，**不动** 38-78 禁区、**不动** 201-206 英文 prompt。§1.3 的两项剩余问题（正则双向误判 / 无条件注入）**Step 2 未处理，待 T8-10** | 1 条哈希（**实测 1 条，与预估一致**） | T8-02 的 43 项行为测试仍全绿 + 新增结构测试 18 项 |
| **3** | ✅ **已完成**（提交 `56803e88d` / `fc345c2c0` / `f7ddf1956` / `0fbd10f3f` / `319c06ff9` / `6105e6350`）`astr_main_agent` 外迁 —— quote **6** → #38；proactive **3** + 2 常量 → #39。**留守 4**（见 §3.2） | 2 条哈希（**实测 2 条**）+ 新增 2 条（#38 #39） | 探针一致 + **AST 断言 `MainAgentBuildConfig(...)` 仍在 `InternalAgentSubStage.initialize()` 内** |
| **4a** | ✅ **已完成**（提交 `cd3fb47fe` / `03540b1f9` / `f18ae84ba` / `e5f196b3d` / `a51f47608`）工具结果落盘族外迁 → **#37**（**方案 a 薄委托**：runner 保留 3 个转发方法，保住上游 `runner._write_tool_result_overflow_file` 实例级 monkeypatch）。runner **2039 → 2018（-21）** | 新增 1 条（#37）+ runner 哈希 1 条（**实测 1+1**） | 探针 MATCH + 结构守卫 5 处齐全 + β xfail 8/8 + 新增 14 case |
| **4b** | ✅ **已完成**（提交 `765346125` / `55806fe02` / `8f2f4e2` / `b228f8b7f` / `9c0774f33` / `538b1377c`）工具循环族外迁 → **#37**：`_track_tool_call_streak` / `_build_repeated_tool_call_guidance` / `_iter_tool_executor_results`，并把前置定义 `_ToolExecutionInterrupted` / `ToolExecutorResultT` 一并搬到 #37（runner 反向 import；**两者不进 `__all__`**）。⛔ **`_materialize_large_tool_result` 按裁决不搬**（monkeypatch 契约）。runner **2018 → 1935（-83）** | **不新增条目（仍 39）**，同步 runner + #37 两条哈希 | 探针 MATCH + 结构守卫 5 处齐全 + β xfail 8/8 + 新增 12 case |
| **4c** | sanitize / `_resolve_tool_exec` 辅助族外迁 | 1 条哈希 | 同上 |
| **4d** | **取消** `_simple_print_message_role` 外迁（调用点 1004/1015 紧贴 984 敏感区） | 0 | — |

Step 0 与 0' 互不依赖，可同批执行。

> **结构守卫的执行保证**（偏离 2 的接受前提）：
> `hook_timing_probe.py` 的 `main()` 在**每次调用** —— `--dump` 与 `--compare` 都算 —— 都会先跑一次
> 符号化 `structural_guard(runner)`，断言 `await self._complete_with_assistant_response(`
> **恰好 5 处**（enhanced 分支 1 / legacy 分支 1 / 无条件 3），并把守卫错误并入 `failures` ⇒ 退出码 `1`。
> 判定**不依赖行号**（向上回看 6 行找 `if [not ]legacy_timing:`），所以拆分后行号漂移不会误报，
> 但少一处 / 多一处 / 分支性质变了会立刻判红。
> ⇒ **Step 4a / 4b / 4c 每一步跑一次 `--compare`，结构守卫就必然执行一遍。**
> 比对范围只含 `events` / `summary` / `mode_symmetry`；`repo_commit` 与 `case.call_site` 是信息字段，不参与比对。

### 2.1 各步外迁清单（调用行号实况，均不落在 984/1100/1142/1166/1340）

| 步 | 函数 | 被调行号 |
|---|---|---|
| 3a | ✅ **外迁 9 个**：`_get_quoted_message_parser_settings` / `_process_quote_message` / `_provider_supports_modality` / `_append_quoted_image_attachment` / `_append_audio_attachment` / `_append_quoted_audio_attachment`（→ **#38**，前三个 `internal.py` 另 import）<br>`_proactive_cron_job_tools` / `_apply_web_search_tools` / `_apply_web_search_citation_prompt` + 常量 `WEB_SEARCH_CITATION_TOOL_NAMES` / `WEB_SEARCH_CITATION_PROMPT`（→ **#39**） | 1547,1627 / 1742 / 1079,1427,1432,1748 / 1582,1638 / 1532 / 1586 / 1779 / 1762 / 1869 |
| 3b | ⛔ **留守 4 个（不可外迁）**：`_append_video_attachment` / `_build_local_mode_prompt` / `_apply_local_env_tools` / `_filter_skills_for_current_config` | 见 §3.2 |
| 4a | ✅ **已执行**（方案 a 薄委托）`_write_tool_result_overflow_file` / `_truncate_tool_result_preview` / `_read_tool_hint` → **#37**（runner 保留 3 个薄委托，保住上游 1990 行的实例级 monkeypatch）| 新增 1 条（#37）+ runner 哈希 1 条 | 探针 + β xfail 8/8 + 调用点仍为 5 |
| 4b | ✅ **已执行**`_track_tool_call_streak` / `_build_repeated_tool_call_guidance` / `_iter_tool_executor_results` → #37（+ 前置定义 `_ToolExecutionInterrupted` / `ToolExecutorResultT`）。⛔ `_materialize_large_tool_result` **不搬**。**#37 `__all__` 最终 6 符号**：`build_repeated_tool_call_guidance` / `iter_tool_executor_results` / `read_tool_hint` / `track_tool_call_streak` / `truncate_tool_result_preview` / `write_tool_result_overflow_file` |
| 4c | `_sanitize_malformed_tool_calls` / `_build_tool_requery_context` / `_build_tool_subset` / `_has_meaningful_assistant_reply` | 724,1890,1922 / 1875,1902 / 1866,1871 / 1897 |

**不得外迁**：`_iter_llm_responses*` (1017，直接决定 yield 顺序)、`_sanitize_contexts_for_provider`
（**241 在 `_complete` 内被调用**）、`_complete_with_assistant_response` 本体与 5 个调用点。
`_get_session_conv` 也**不动**（被 `cron/manager.py` + `astr_agent_tool_exec.py` import，动它会牵连额外文件）。

## 3. 39 条登记清单（定稿）

现有 36 条**全部保留**，新增 3 条：

| # | 新增模块 | 被谁 import | 何时登记 |
|---|---|---|---|
| **37** | `astrbot/core/agent/runners/tool_loop_support.py` | 仅 `tool_loop_agent_runner.py`（已登记） | Step 4a。**\#37 是单模块，由 4a / 4b / 4c 共用**：4b / 4c 只往里加函数并同步 runner 哈希，**不再新增台账条目** |
| **38** | `astrbot/core/astr_main_agent_quote.py`（**quote 6 函数**） | `astr_main_agent.py`（已登记）+ `internal.py`（已登记） | Step 3 |
| **39** | `astrbot/core/astr_main_agent_proactive.py`（**proactive 3 函数 + 2 常量**） | 仅 `astr_main_agent.py`（已登记） | Step 3 |

> **给后人的说明（#38）**：`#38` 被 pipeline 层的 `internal.py` import，
> 属**既有耦合的延续** —— `internal.py` 本就从 `astr_main_agent.py` import
> `_get_quoted_message_parser_settings` / `_process_quote_message` / `_provider_supports_modality`，
> 外迁只是换了来源模块，**不是新增架构耦合**。

### 3.2 实际外迁 9 / 留守 4（2026-10-14 定稿）

原定 13 个，实施时发现**上游测试的软锁定面比估计的宽**：不只是 `ama.<函数名>` 读名，
还有 `patch` / `monkeypatch.setattr` 目标。`patch` **只重绑 `astr_main_agent` 命名空间里的名字**，
函数搬到新模块后全局名解析走新模块 ⇒ 补丁失效，**re-export 救不了**。

| 类别 | 函数 | 锁定源 |
|---|---|---|
| ✅ 外迁 7 | `_append_quoted_image_attachment` / `_append_audio_attachment` / `_append_quoted_audio_attachment` / `_get_quoted_message_parser_settings` / `_process_quote_message` / `_provider_supports_modality` / `_apply_web_search_citation_prompt` | 无 |
| ✅ 外迁 2（需 `# noqa: F401` 保名） | `_proactive_cron_job_tools`（`FutureTaskTool`）／ `_apply_web_search_tools`（`BaiduWebSearchTool` / `Firecrawl×2` / `normalize_legacy_web_search_config`） | 上游断言读 `module.X` 同名对象 |
| ⛔ **留守 4** | `_append_video_attachment` | `patch("astrbot.core.astr_main_agent.logger")` ×5，断言 `mock_logger.error.call_count == 1` |
| ⛔ 同上 | `_build_local_mode_prompt` | `patch("...astr_main_agent.resolve_windows_shell")` ×3 |
| ⛔ 同上 | `_filter_skills_for_current_config` | `monkeypatch.setattr(module, "star_registry", …)` ×2 |
| ⛔ 同上 | `_apply_local_env_tools` | 它调用 `_build_local_mode_prompt`；后者留守 ⇒ 前者留守才不产生回边 |

**明确拒绝的替代方案**：给留守函数加「函数内延迟反向导入」（`from astrbot.core.astr_main_agent import logger`）
可以凑满 13 个，但会新增 `astr_main_agent_quote/_proactive → astr_main_agent` 的**回边耦合**，
违反本节"#38 不是新增架构耦合"的定性与「兼容优先、零冲突」铁律 ⇒ **不采用**。

⇒ 行数：**1905 → 1725（−180 / −9.4%）**，而非原估的 1624 / −15%（实测值见 §2 第 3 行）。

> **技术债（Step 3 留下，待后续单独排期）**
> 1. **4 个函数因上游 patch 软锁定无法外迁**：`_append_video_attachment`（`ama.logger`）、
>    `_build_local_mode_prompt`（`ama.resolve_windows_shell`）、`_filter_skills_for_current_config`
>    （`ama.star_registry`）、`_apply_local_env_tools`（依赖上者）。除非接受回边耦合，否则动不了。
> 2. **`astr_main_agent.py` 因上游测试软锁定（含 re-export）无法彻底瘦身**：外迁 9 个后仍 **1725 行**，
>    剩余大头 `build_main_agent`(248) / `collect_initial_request`(220) / `_ensure_persona_and_skills`(178) 未拆。
> 3. **`_append_video_attachment` 与 `_apply_local_env_tools` 全仓零直接覆盖**（既有债务，Step 3 未补）。

### 3.1 完整 39 条（现有 36 + 新增 3）

```
 1. astrbot/api/_bridge.py
 2. astrbot/api/content/__init__.py
 3. astrbot/api/delivery/__init__.py
 4. astrbot/api/embedding/__init__.py
 5. astrbot/api/media/__init__.py
 6. astrbot/api/permissions/__init__.py
 7. astrbot/api/proactive/__init__.py
 8. astrbot/api/runtime/__init__.py
 9. astrbot/api/turns/__init__.py
10. astrbot/core/agent/runners/tool_loop_agent_runner.py
11. astrbot/core/agent/tool.py
12. astrbot/core/astr_agent_run_util.py
13. astrbot/core/astr_agent_tool_exec.py
14. astrbot/core/astr_main_agent.py
15. astrbot/core/code_delivery_policy.py
16. astrbot/core/config/agent_runner.py
17. astrbot/core/config/default.py
18. astrbot/core/cron/manager.py
19. astrbot/core/pipeline/context_utils.py
20. astrbot/core/pipeline/process_stage/follow_up.py
21. astrbot/core/pipeline/process_stage/method/agent_sub_stages/image_input.py
22. astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py
23. astrbot/core/pipeline/process_stage/stage.py
24. astrbot/core/pipeline/respond/stage.py
25. astrbot/core/pipeline/scheduler.py
26. astrbot/core/platform/sources/aiocqhttp/aiocqhttp_message_event.py
27. astrbot/core/provider/entities.py
28. astrbot/core/provider/sources/openai_source.py
29. astrbot/core/star/maintenance.py
30. astrbot/core/star/star_manager.py
31. astrbot/core/star/updater.py
32. astrbot/core/tools/computer_tools/python.py
33. astrbot/core/tools/computer_tools/shell.py
34. astrbot/core/tools/computer_tools/util.py
35. astrbot/core/utils/direct_turns.py
36. astrbot/dashboard/services/plugin_service.py
37. astrbot/core/agent/runners/tool_loop_support.py          <- 新增 (Step 4a)
38. astrbot/core/astr_main_agent_quote.py                    <- 新增 (Step 3)
39. astrbot/core/astr_main_agent_proactive.py                <- 新增 (Step 3)
```

`tests/maintained/test_manifest_guard.py` 的 `EXPECTED_ENTRY_COUNT` 需在 Step 3/4a 同步（36 → 38 → 39）。

## 4. 哈希必变文件（6 个，均为已登记文件）

| 文件 | 变动步 | 原因 |
|---|---|---|
| `astrbot/core/pipeline/process_stage/follow_up.py` | Step 1 | 去重 + `self_id` 统一 |
| `astrbot/core/utils/direct_turns.py` | Step 1 | 复用判定（共享 `other` 谓词的落点） |
| `astrbot/core/code_delivery_policy.py` | Step 2 | 结构整理 |
| `astrbot/core/astr_main_agent.py` | Step 3 | 外迁 |
| `astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py` | Step 3 | import 行改指向 #38 |
| `astrbot/core/agent/runners/tool_loop_agent_runner.py` | Step 4a/4b/4c | 外迁（每步都要同步一次） |

哈希口径 = **文件磁盘字节**（`hashlib.sha256(Path(p).read_bytes())`），写回必须 `write_bytes`（LF）。

## 5. 顺序探针

- **脚本**：`maintained/tools/hook_timing_probe.py`（与 `check_drift` / `apply_patches` 同目录同风格）
- **基线落盘**：`maintained/baselines/hook_timing/<shortsha>.json`
- **用法**：`--dump <path>` / `--compare <path>`，退出码 `0/1/2`（与 `check_drift` 一致）
- **schema**：

```json
{
  "schema": 1,
  "generated_by": "maintained/tools/hook_timing_probe.py",
  "repo_commit": "<git rev-parse HEAD 短 sha>",
  "cases": [
    {
      "case": "skills_like_requery",
      "call_site": 1142,
      "mode": "enhanced",
      "events": [
        {"i": 0, "kind": "llm_result", "text": "Let me check.", "hook_done": false},
        {"i": 1, "kind": "llm_result", "text": "<FINAL>", "hook_done": true}
      ],
      "summary": {
        "hook_done": true,
        "provider_calls": 2,
        "done": true,
        "hook_index": 1,
        "first_final_yield_index": 1
      }
    }
  ]
}
```

- **β 的真正不变量（只比相对关系，不比绝对索引）**：
  - `enhanced` ⇒ `hook_index < first_final_yield_index`
  - `legacy`   ⇒ `hook_index > first_final_yield_index`
- `repo_commit` 允许逐次变化；`events` 与 `summary` 必须逐字段一致。

## 6. 零保护 case 清单（Step 0 同步落盘，Step 4 每步逐项核对）

β 8 项 xfail **全部是同一测试函数** `tests/test_tool_loop_agent_runner.py:1751`
`test_skills_like_requery_reply_reaches_stream_bridge_once`
（`(streaming, stream_to_general, show_reasoning)` 4 组 × `use_result_chain` 2 组），
核心断言 `hooks_at_emission == [False, False] + ([True, True] if streaming else [])`。
⇒ **只有 case 1142/1166 被 xfail 机械保护**；下列 3 个 case **零 xfail 覆盖**：

| case | 调用点 | 为何零保护 | 三重验证的具体执行方式 |
|---|---|---|---|
| 图片不可用早退 | **984** | fork 新增路径，上游无对照 ⇒ 上游测试不存在 | ① 探针：构造 `req.image_input_unavailable=True` 的一步流，断言 `events` 序列与基线一致（钩子在第 1 个 yield 之前完成）<br>② 结构守卫：`_complete_with_assistant_response` 调用点计数 == 5，且 984 仍存在且无条件调用<br>③ 逐点时序断言：新增用例断言"该路径下 `hook_done` 在第 1 个 `llm_result` 时已为 True" |
| 无工具调用 | **1100** | 与上游逐点相同 ⇒ 上游测试**通过**而非 xfail，改坏了才会红 | ① 探针：普通一步回复流，`events` 序列比对<br>② 结构守卫：1100 仍在 `if not llm_resp.tools_call_name:` 之后，且**不**带 `legacy_timing` 条件<br>③ 逐点时序断言：断言该路径在 enhanced / legacy 两种模式下**结果完全相同**（这是"一行未动"的直接证据） |
| 工具连败末轮补生成 | **1340** | fork 新增路径，上游无对照 | ① 探针：构造同工具同参数连败 3 次的流，`events` 序列比对<br>② 结构守卫：1340 无 `legacy_timing` 分支（grep 断言该行上下文不含 `legacy_timing`）<br>③ 逐点时序断言：断言 enhanced / legacy 两种模式下**结果完全相同** |

**Step 4 每一步（4a/4b/4c）的验收动作**：探针 `--compare` 通过 → β xfail 仍 8/8 → 上表三行逐项核对并留痕。

## 7. 禁区（全程不变）

- **T8-10** 提权逻辑：**零触碰**。⚠️ 行号已订正（2026-10-13 取证）：旧记载的 `code_delivery_policy.py:80`
  **是错的**（该行现为**空行**）—— 那组行号写于 `d88b38c3f` 时代，`cecdab218` 让全文整体上移 **8 行**。
  **现况**：`execution_denial` **整段 38–78 行**为禁区（T8-10 + T8-13 双重），其中误放行分支
  `然后|并|再|并且` 现为 **72 行**；`SAFETY_REFUSAL_PATTERN` 现为 **11–19 行**；T8-13 载体
  （无条件 `get_sender_id()`）现为 **48 行**。
- **T8-13** 测试脆弱性（`execution_denial` 无条件读 `get_sender_id()`）：**仅记录**
- **上游测试文件**：零修改（已复核 `git diff --name-status baseline/v4.28.2 -- tests/ | grep -v "^A"` = 空）
- **上游基线与 API 调用**：零变更；`astrbot/api/**` 上游符号由 `test_api_frozen.py` 守护
- **台账**：仅在对应步骤按上表同步，**不提前写**

## 8. 验收口径（每步都要满足）

`tests/maintained` 全绿（**2026-10-14 Step 3 后实测：349 passed + 1 skipped，26 个测试文件 + conftest**；
演进：Step 0 前 303+1 / 22 文件 → Step 1 后 317+1 / 24 文件 → Step 2 后 335+1 / 25 文件 →
Step 3 后 349+1 / 26 文件 → Step 4a 后 363+1 / 27 文件 → Step 4b 后 375+1 / 27 文件，只增不减）／上游 `295 passed + 17 xfailed` 不变（含 β xfail 8/8）／
ruff `check` 干净、`format --check` 仅剩 `config/agent_runner.py` 与 `config/default.py` 两个已同意延后的文件／
双端（实例 + 仓）NO DRIFT／探针一致／β xfail 8/8。
