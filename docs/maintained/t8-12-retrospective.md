# T8-12 复盘：4 文件拆分重写

> **状态：已完成并结项**（2026-10-13 ~ 2026-10-15）。
> 起点 `57bacfc09`，终点 `46af7b8dc`，共 **44 个提交**，台账 **36 → 39**，
> `tool_loop_agent_runner.py` **2039 → 1905**。
>
> **本文件是复盘，不是证据。** 凡事实主张，一律以 `git log -S` / `git diff baseline/v4.28.2` /
> 文件实况读取为准 —— 这一条在本轮被反复验证（见 §2）。

## 1. 各步总结

| 步 | 内容 | 结果 | 主要提交 |
|---|---|---|---|
| **0** | β 探针（`maintained/tools/hook_timing_probe.py`）+ 5 case 基线 + 零保护清单 | ✅ 基线 `maintained/baselines/hook_timing/57bacfc09.json`；结构守卫符号化（不依赖行号） | `3a1bccdc8` |
| **0'** | 文档订正：`hook-timing-impact.md:16` 的"只延后 1130/1325" | ✅ 订正为"只延后 1130（现 1142/1166）" | `977872dd9` |
| **1** | `follow_up` 去重 + `self_id` 统一（复用 `direct_turns`） | ✅ 抽 `self_id_of` / `mentions_other` / `mentions_self`；**零行为变更** | `f1dc62650` |
| **2** | `code_delivery_policy` 结构整理（**口径 B**：正则字符零改动、不许搬动） | ✅ 抽 `_task_text` / `_drop_execution_tools`；T8-10 禁区零触碰 | `787700da0` |
| **3** | `astr_main_agent` 外迁 → #38 / #39 | ⚠️ **原定 13 个，实迁 9 个**（4 个因上游 patch 软锁定留守） | `fc345c2c0` `f7ddf1956` `0fbd10f3f` |
| **4a** | 工具结果落盘族 → **#37** | ✅ 3 个函数；runner 保留 3 个薄委托 | `03540b1f9` `f18ae84ba` |
| **4b** | 工具循环族 → #37（+ 前置定义搬家） | ✅ 3 个函数 + `_ToolExecutionInterrupted` / `ToolExecutorResultT`；`_materialize_large_tool_result` **按裁决不搬** | `765346125` `55806fe02` |
| **4c** | sanitize / `_resolve_tool_exec` 辅助族 → #37 | ✅ 4 个函数；`_resolve_tool_exec` 留守 | `fd5ffef34` `0c1bca2d2` |
| **4d** | `_simple_print_message_role` 外迁 | ⛔ **取消**（调用点紧贴 984 敏感区，收益 < 风险） | — |

## 2. 踩过的坑与自修

### 2.1 取证类（这条救了整个任务）

| # | 坑 | 处置 |
|---|---|---|
| 1 | **plan §7 的 `code_delivery_policy.py:80` 是错的** —— 实况为空行。那组行号写于 `d88b38c3f` 时代，`cecdab218` 让全文上移 **8 行** | 订正为 38–78 禁区 + 误放行分支现 **72 行**（提交 `9d892d26d`）|
| 2 | **plan §3 的"构造语句仍在 `__init__` 内"是错的** —— 实况在 `InternalAgentSubStage.initialize()`（不是 `__init__`）| 改用 **AST 断言**按函数名判定 |
| 3 | **plan §1.2 称 handover.md 也有错误记载** —— grep 实况**零命中**，不成立 | 改为"`hook-timing-impact.md:16` 是唯一错误源" |
| 4 | AST 断言的 `EXPECTED_BUILD_KEYWORDS` 我按不完整阅读写了 17 个 | AST 实取为 **19 个**（补 `timezone` / `max_quoted_fallback_images`）|

> **教训**：plan / handover 里的行号在本轮被证明错 **5 处**。凡引用行号，一律先 `git show` 核验。

### 2.2 实现类

| 步 | 坑 | 处置 |
|---|---|---|
| 2 | `_task_text` 首版只返回 `(current_text, text)`，但 137 行还要用 `original` ⇒ **ruff F821 + 3 项行为测试红** | 改为返回 **3 元组** |
| 3 | **上游测试软锁定面比报告宽**：不只是 `ama.<函数名>` 读名，还有 `patch` / `monkeypatch.setattr` 目标（`ama.logger` ×5、`ama.resolve_windows_shell` ×3、`ama.star_registry` ×2）| 4 个函数留守；其余靠 **re-export + 显式 `__all__`** 保住上游 295 |
| 3 | 常量循环导入：`WEB_SEARCH_CITATION_*` 若由新模块从 `astr_main_agent` 取 ⇒ 成环 | 常量**随函数搬进 #39**，`astr_main_agent` re-export |
| 4a | 新模块漏 import `logger` / `Reply` | ruff **F821 立刻抓出**（与 Step 2 同一机制）|
| 4b | 剪除脚本用"降序区间删除"因行号位移**切错函数**（SyntaxError）| 改用**行掩码一次性过滤** |
| 4b | `ruff format` 在 `async def` 前吃了一个空行 | 单独一个 style 提交 + 再同步哈希 |
| 4c | 签名断言首版"两侧都剥首参"，而 `_build_tool_subset` 的 support 侧**没有 runner 首参** ⇒ 红 | 改为**两条各自动态判定**（见 §3.5）|
| 4c | `copy` 在 runner 里变未使用 | ruff --fix 移除（#37 自己 import）|

## 3. 收获（对后续任务有价值的经验）

### 3.1 探针 + 符号化结构守卫 = 拆分的安全网
`hook_timing_probe.py` 的 `structural_guard()` 在**每次调用**（`--dump` 与 `--compare` 都算）都跑，用"向上回看 6 行找 `if [not ]legacy_timing:`"的符号化方式判定，**不依赖行号**。
⇒ 行号漂移不误报，少一处 / 多一处 / 分支性质变了立刻判红。这是能在 β 宿主文件上动刀的前提。

### 3.2 基线必须硬编码，AST 只负责取实际值
`EXPECTED_BUILD_KEYWORDS` 是硬编码的 19 个字面量，AST 只从源码实取当前值再比对。
⇒ 若改成"动态提取再自己比自己"就成了自证，失去钉子意义。

### 3.3 "零改动"要用 AST 逐行取证，不能靠看 diff
每步都跑一次"`_step` / `_materialize_large_tool_result` / `_resolve_tool_exec` 等留守区的**逐行内容完全相同 = True** 断言。
⇒ β 五调用点**全程只做整体位移、彼此间距不变**，这是"没动 β"最硬的证据（比人眼看 diff 可靠得多）。

### 3.4 薄委托是"外迁 + 保上游契约"的通用解
上游测试靠三类方式锁定符号，薄委托能全覆盖：

| 锁定方式 | 例子 | 薄委托是否解决 |
|---|---|---|
| 实例级 monkeypatch | `runner._write_tool_result_overflow_file` | ✅（`monkeypatch` 需要属性存在，薄委托提供）|
| 模块别名读名 | `ama._provider_supports_modality` | ✅（re-export + `__all__`）|
| **测试直调** | `runner._build_tool_requery_context(["test_tool"])` | ✅（同名方法 + 位置参数签名保持）|

### 3.5 签名一致性断言要"两侧各自动态判定"
```python
is_static = isinstance(inspect.getattr_static(Runner, method_name), staticmethod)
method_params = list(method.parameters.values())
if not is_static:                                   # 非 staticmethod 才剥 self
    method_params = method_params[1:]
function_params = list(function.parameters.values())
if function_params and function_params[0].name == "runner":   # support 侧按首参名决定
    function_params = function_params[1:]
```
⇒ 不硬编码"哪些是 staticmethod"、"哪些带 runner"，将来 #37 改签名或加函数都自动适配。

### 3.6 先文档后代码 + 一改动一提交
本轮 44 个提交，每步都是"文档 → 代码 → 测试 → 台账 → 文档标 ✅"。
⇒ 任何一步都可以单独回滚；复盘时能精确对应。

### 3.7 边界报告制度值得保留
Step 2 / 3 / 4a / 4b / 4c 每步执行前先出**只读边界报告**，用户确认后再动手。
⇒ Step 3 就是在执行中才发现软锁定面被低估，及时**回滚**（工作区干净、上游恢复绿）后重报，避免了带病推进。

## 4. 技术债清单

| # | 债务 | 影响 | 建议时机 |
|---|---|---|---|
| 1 | **4 个函数因上游 patch 软锁定无法外迁**：`_append_video_attachment`（`ama.logger`）、`_build_local_mode_prompt`（`ama.resolve_windows_shell`）、`_filter_skills_for_current_config`（`ama.star_registry`）、`_apply_local_env_tools`（依赖上者）| `astr_main_agent.py` 无法进一步瘦身 | 除非接受"函数内延迟反向导入"的回边耦合（本轮**明确拒绝**），否则动不了 |
| 2 | **3 个大函数未拆**：`build_main_agent`(248) / `collect_initial_request`(220) / `_ensure_persona_and_skills`(178) | `astr_main_agent.py` 仍 **1725 行** | 单独立项 |
| 3 | **ruff format 遗留**：`astrbot/core/config/agent_runner.py` / `astrbot/core/config/default.py` 需重排（HEAD 既存，非本轮引入；根因是历史提交没跑 format，非版本差异 —— pre-commit 与 pyproject 都锁 `0.15.22`）| `ruff format --check .` 不干净 | 单独 format-only 提交（注意会带出大 diff，需先 `--diff` 确认纯格式）|
| 4 | **async generator 薄委托例外**：`_iter_tool_executor_results` 无法一行 `return`（体内有 `yield`），薄委托是两行 `async for + yield` | 与"薄委托统一一行转发"的约定不一致 | 已记入 plan §2；后续遇到 async generator 沿用此形态 |
| 5 | **内部符号不进 `__all__` 的规则**：`_ToolExecutionInterrupted` / `ToolExecutorResultT` 由 #37 定义、runner 反向 import，但**不进 `__all__`** | 将来若有人按 `__all__` 判断"#37 有什么"会漏掉它们 | 已由测试断言"存在但不在 `__all__`"钉住 |
| 6 | **`_append_video_attachment` / `_apply_local_env_tools` 全仓零直接覆盖** | 改动这两个函数无测试兜底 | 若将来要动它们，先补测试 |
| 7 | **`astr_main_agent.py` 因上游测试软锁定（含 re-export）无法彻底瘦身** | 外迁 9 个后仍 1725 行 | 与 #1 / #2 一起评估 |

## 5. 数字总览

| 项 | 起点 | 终点 |
|---|---|---|
| 台账条目 | 36 | **39**（新增 #37 / #38 / #39）|
| `tool_loop_agent_runner.py` | 2039 | **1905**（−134 / −6.6%）|
| `astr_main_agent.py` | 1908 | **1725**（−183 / −9.6%）|
| `code_delivery_policy.py` | 212 | 240（内部整理后略增，因 docstring）|
| `follow_up.py` / `direct_turns.py` | 264 / 341 | 256 / 384 |
| maintained 测试 | 303 passed + 1 skipped（22 文件） | **390 passed + 1 skipped**（27 文件）|
| 上游口径 | 295 passed + 17 xfailed | **不变**（β xfail 8/8 全程保持）|
| 新模块 | — | #37 = 334 行、#38 = 156 行、#39 = 114 行 |
