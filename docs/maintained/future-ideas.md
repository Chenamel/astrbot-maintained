# 未来想法与调研（2026-10-18）

> 来源：用户《astrbot修改计划.txt》的三条想法。本文档记录**调研结论**与**是否自建**的判断，
> 避免重复造轮子，也避免和已装插件打架。

## 想法一：动态上下文 + 拟人回复（让模型看到历史、自行决定回复形式）

拆成 4 块后的可行性：

| 子项 | 现状 | 判断 |
|---|---|---|
| a. 看到提问用户与聊天历史 | core 无历史消息能力，只有会话内轮次上下文 | 已由插件覆盖 |
| b. 上下文不足时“爬楼”/搜历史 | 平台基类**无**统一 API；aiocqhttp 有 `get_client()`（CQHttp）⇒ QQ 侧可发原始 OneBot 动作 | 技术上可行，但生态已有插件 |
| c. 模型决定回复谁 / 是否 @ / 是否引用 | `Reply` / `At` 组件齐全，但由代码决定，模型无法表达 | ⭐ **唯一真缺口，值得 fork 做** |
| d. 更拟人（接近 maibot） | — | 综合效果，是验收目标不是子项 |

### 生态调研（重要：不要重复造）

- **enhance_mode**（已装）：React 群聊上下文 + **Memory RAG** + 主动回复 ⇒ 已覆盖 a/b
- **livingmemory**（已装）：长期记忆（偏好/人物/计划）
- **CyberArchaeology（赛博考古）**：embedding 历史消息检索，支持 `/ca load_history 200 500`
  **批量导入历史消息**（即“爬楼”），仅支持 aiocqhttp
- **OpenViking Memory**：首次遇到场所时**回填平台历史消息**
- **SpectreCore（影芯）**：读空气（判断何时回复/沉默）、@ 智能理解、引用上下文关联
- **Memory Companion**：分层记忆包注入，不粗暴塞回模型

⇒ **结论**：a、b、d 交给插件；fork 只做 **c（回复形式决策通道）**，作为**底层能力**
落 `astrbot/api/**`，**默认关闭**，供插件调用。

## 想法二：更真实稳定的断句

**上游已有完整实现**（默认关闭，属隐藏配置）：`platform_settings.segmented_reply`

- `enable`（默认 false）、`only_llm_result`
- `interval_method`: `random` / `log`（log 按字数算等待，更像人打字）
- `interval`、`log_base`、`words_count_threshold`
- `split_mode`: `regex` / `words`，`regex` 可自定义，另有 `content_cleanup_rule`
- 另有 `unsupported_streaming_strategy: "realtime_segmenting"`

实现位置：`astrbot/core/pipeline/respond/stage.py`。

**状态：搁置**（用户判断：官方分段不如插件，测试优先级低）。
若将来要做，正确姿势是**给 `split_mode` 增加一种「模型标记分句」**，而不是重写。

⚠️ 注意：用户已装 **splitter（对话分段PRO）** 在做分段，两者同时开可能**重复分段**。

## 想法三：兼容前提下优化核心与性能

已做过一批（T8-12 等），收益递减；改 core 越多、合上游越痛。
**状态：按需**，遇到具体瓶颈再做，不主动开。

## 本机插件完整扫描（2026-10-18，17 个）

用户提醒"是不是已有 @ 工具" ⇒ 全量扫描，结论：**①②③ 的想法本机插件几乎都覆盖了**。

| 插件 | 职责 | 覆盖哪个想法 |
|---|---|---|
| `astrbot_plugin_AtTool` | 给模型 `get_group_members` 工具 + 把模型输出的 `[mention:ID]` 标签转成真实 At 组件 | ⭐ **覆盖①的「@ 谁」** |
| `astrbot_plugin_astrbot_enhance_mode` | React 群聊上下文、`enhance_memory_rag_read/write`、封禁、主动回复、WebUI | ⭐ **覆盖①的「看上下文 / 搜历史（爬楼）」** |
| `astrbot_plugin_self_learning` v4.3.0 | 采集并注入上下文，表达风格 / 群组黑话 / 社交关系 / 长期记忆 / **人格演化** | ⭐ **覆盖①的「拟人」** |
| `astrbot_plugin_livingmemory` | 长期记忆（偏好/人物/计划） | 覆盖①的记忆部分 |
| `astrbot_plugin_splitter` | 分段发送 | ⭐ **覆盖②断句** |
| `astrbot_plugin_wake_enhance` | 唤醒判定（正则、持续对话、白名单） | 覆盖①的"何时回复" |
| `astrbot_plugin_proactive_chat` | 主动聊天 | 与官方主动回复重叠 |
| `astrbot_plugin_qq_group_daily_analysis` | 群日报分析（读群消息） | 与历史检索重叠 |
| 其余（content_safety_guard / debounce / help_typst / image_studio / music / parser 链接解析 / random_likes / uapipro_toolbox / meme_manager） | 各自领域 | 无关 |

### 修正后的判断

- **①c（回复形式决策）** 里：
  - **「@ 谁」已被 AtTool 覆盖**（查成员 + `[mention:ID]` 标签 → 真实 At 组件）
  - 「搜历史」已被 `enhance_memory_rag_read` 覆盖
  - 「拟人」已被 `self_learning` 覆盖
  - **唯一未覆盖的只剩「让模型主动引用（Reply）某条消息」** —— 单点，价值存疑
  ⇒ **①c 优先级下调**，暂不动工
- ⚠️ **更值得警惕的是重叠**：17 个插件里至少 6 个在同时做上下文 / 记忆 / 拟人
  （enhance_mode、livingmemory、self_learning、proactive_chat、qq_group_daily_analysis、
  content_safety_guard）⇒ **可能互相打架**，这比"缺功能"更可能是表现不稳的原因
- **fork 的定位回到**：只补**插件确实做不到**的底层能力，且要有证据

### 下一步建议（待用户定）

1. 做一次**只读链路盘点**：这些插件分别在什么时候注入上下文、谁改消息链、谁在做分段/主动
   ⇒ 先搞清楚实际链路，再决定要不要动 fork
2. 若盘点后确认"引用"是唯一缺口 ⇒ 再评估值不值得为它单独建通道
