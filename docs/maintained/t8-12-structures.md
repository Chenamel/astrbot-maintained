# T8-12 关键结构索引

> 用途：新对话接手 T8-12 时的**结构速查表**。只放结构，不放叙述；
> 完整论证与理由见 `docs/maintained/t8-12-plan.md`。
> **本文件为交接用索引，凡涉及代码现状的事实主张，以 `git log -S` / `git diff baseline/v4.28.2` / 文件实况读取为准，本文件不作证据。**

## 1. β 敏感调用点（5 处，逐点保真）

| 调用点（现行号） | 旧行号 | legacy 分支 | 性质 | 上游对照 |
|---|---|---|---|---|
| 984 | 977 | ❌ 无 | fork 新增（图片不可用早退） | 无 |
| 1100 | 1093 | ❌ 无 | 与上游逐点相同 | 有（基线 913） |
| **1142** | 1130 | ✅ **先**（`if not legacy_timing`） | **enhanced＝本 fork 优化**（钩子先于回复） | 有 |
| **1166** | 1130 | ✅ **后**（`if legacy_timing`） | **legacy＝上游位置**（钩子后于回复） | 有 |
| 1340 | 1325 | ❌ 无 | fork 新增（工具连败末轮补生成） | 无 |

- 判定开关：`self.hook_timing_mode == "legacy"`（runner `:1140`）
- 完成钩子本体：`_complete_with_assistant_response` 定义于 runner **202–311**
- **git 实况**：`git log -S"legacy_timing" -- astrbot/core/agent/runners/tool_loop_agent_runner.py` ⇒ 唯一 commit `109c0130a`（只动 1130 一处）

## 2. 探针 5 case → xfail 覆盖

| case | 调用点 | 覆盖的 xfail | 说明 |
|---|---|---|---|
| image_unavailable | 984 | **0** | fork 新增，上游无对照 |
| no_tool_call | 1100 | **0** | 与上游相同 ⇒ 上游测试通过，不产生 xfail |
| requery_enhanced | 1142 | **β 全部 8 项** | 同一测试函数 × 8 组参数 |
| requery_legacy | 1166 | **β 全部 8 项** | 同上 |
| tool_failure_final | 1340 | **0** | fork 新增，上游无对照 |

- β 8 项 = `tests/test_tool_loop_agent_runner.py:1751`
  `test_skills_like_requery_reply_reaches_stream_bridge_once`
  （`(streaming, stream_to_general, show_reasoning)` 4 组 × `use_result_chain` 2 组）
- 核心断言：`hooks_at_emission == [False, False] + ([True, True] if streaming else [])`
- **不变量**：`enhanced ⇒ hook_index < first_final_yield_index`；`legacy ⇒ hook_index > first_final_yield_index`

## 3. 零保护 case（984 / 1100 / 1340）三重验证

| case | ① 探针基线 | ② 结构守卫 | ③ 逐点时序断言 |
|---|---|---|---|
| **984** | 构造 `image_input_unavailable=True` 一步流，`events` 与基线逐字段比对 | 调用点计数 == 5；984 存在且**无条件**调用 | 第 1 个 `llm_result` 时 `hook_done` 已为 True |
| **1100** | 普通一步回复流，`events` 比对 | 1100 位于 `if not llm_resp.tools_call_name:` 之后，且**不带** `legacy_timing` 条件 | enhanced 与 legacy 两种模式结果**完全相同** |
| **1340** | 同工具同参数连败 3 次流，`events` 比对 | 1340 上下文 grep 不含 `legacy_timing` | enhanced 与 legacy 两种模式结果**完全相同** |

Step 4a / 4b / 4c **每一步**都要：探针 `--compare` 通过 → β xfail 仍 8/8 → 上表三行逐项核对留痕。

## 4. 台账：新增 3 条 + 哈希必变 6 条

| # | 新增模块 | 被谁 import | 登记时机 |
|---|---|---|---|
| 37 | `astrbot/core/agent/runners/tool_loop_support.py` | 仅 `tool_loop_agent_runner.py` | Step 4a |
| 38 | `astrbot/core/astr_main_agent_quote.py` | `astr_main_agent.py` + `internal.py` | Step 3 |
| 39 | `astrbot/core/astr_main_agent_proactive.py` | 仅 `astr_main_agent.py` | Step 3 |

> #38 被 pipeline 层 `internal.py` import 属**既有耦合的延续**（`internal.py` 本就 import `astr_main_agent`），非新增架构耦合。

| 哈希必变文件 | 变动步 | 原因 |
|---|---|---|
| `astrbot/core/pipeline/process_stage/follow_up.py` | 1 | 去重 + `self_id` 统一 |
| `astrbot/core/utils/direct_turns.py` | 1 | 共享 `other` 谓词落点 |
| `astrbot/core/code_delivery_policy.py` | 2 | 结构整理 |
| `astrbot/core/astr_main_agent.py` | 3 | 外迁 |
| `astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py` | 3 | import 改指向 #38 |
| `astrbot/core/agent/runners/tool_loop_agent_runner.py` | 4a / 4b / 4c | 外迁（每步同步一次） |

- 现状 **36 条** → 目标 **39 条**；`EXPECTED_ENTRY_COUNT` 在 Step 3（→38）、Step 4a（→39）同步
- 哈希口径 = 文件磁盘字节；写回用 `write_bytes`（LF）

## 5. 步骤表（一步一行）

| 步 | 内容 | 台账 | 验收 |
|---|---|---|---|
| 0 | β 探针落地 + 5 case 基线 + 零保护清单 | 0 | 基线 JSON 落盘，5 case 全通过 |
| 0' | 订正 handover + `hook-timing-impact.md:16` | 0 | 双端仍 36 条 NO DRIFT |
| 1 | `follow_up` 去重 + `self_id` 统一 | 2 条哈希 | 探针一致 + maintained 304 |
| 2 | `code_delivery_policy` 结构整理（**正则零触碰**） | 1 条哈希 | T8-02 的 43 项仍全绿 |
| 3 | `astr_main_agent` 外迁 quote / proactive 两组 | 2 条哈希 + 新增 2 条 | 探针一致 + 断言 `internal.py:139` 构造语句仍在 `__init__` 内 |
| 4a | 外迁工具结果落盘族（534 / 532 / 557） | 新增 1 条（#37） | 探针 + β 8/8 + 调用点仍 5 |
| 4b | 外迁工具循环族（1678 / 1685,1702,1716,1739 / 1534 / 1593） | 1 条哈希 | 同上 |
| 4c | 外迁 sanitize / `_resolve_tool_exec` 辅助族（724,1890,1922 / 1875,1902 / 1866,1871 / 1897） | 1 条哈希 | 同上 |
| 4d | **取消** `_simple_print_message_role` 外迁（1004/1015 紧贴 984） | 0 | — |

**不得外迁**：`_iter_llm_responses*` (1017)、`_sanitize_contexts_for_provider`（241 在 `_complete` 内被调用）、
`_complete_with_assistant_response` 本体与 5 个调用点、`_get_session_conv`（牵连 cron/exec 两个文件）。

## 6. 铁律 + 禁区（浓缩版）

- T8-10 提权逻辑：**零触碰**｜T8-13 测试脆弱性：**仅记录**
- 上游测试文件：零修改｜上游基线与 API：零变更
- 台账：仅在对应步骤同步，**不提前写**
- β 五调用点：逐点保真，`_complete_with_assistant_response` 本体不动
- 六铁律：新能力只落 `astrbot/api/**`；先文档后代码；一改动一提交；无测试不进阶段 4+；改 core 同步台账哈希；不动主动回复开关
- 每步停下汇报 ≤10 行等确认，**禁止连推**
- 验收：maintained 304 只增不减｜上游 `295 passed + 17 xfailed`｜ruff 干净｜双端 NO DRIFT｜探针一致｜β xfail 8/8
