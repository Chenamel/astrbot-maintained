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

---

# 主动回复插件：完全重做（用户计划，后续新对话开工）

## 用户的诊断（2026-10-19，比我之前的猜测准）
群友觉得“不太聪明”的真正原因 = **主动回复**，三个具体症状：
1. **触发时机不对**：莫名其妙冒出来说话
2. **上下文缺失**：开口就是没信息量的“问问问”
3. **多模态丢失**：图就在上面，主动回复时被忽略

外加**协议诉求**：需要一个**有开源主动权**的插件；
现有的（enhance_mode 的主动回复，魔改版）**协议上不合规** ⇒ 完全重写，不魔改他人代码。

## ⚠️ 归因修正（2026-10-19 深度排查后推翻前一轮结论）

前一轮曾判断“元凶是 wake_enhance 持续唤醒”——**该判断错误，已推翻**。深度排查结论：

1. **看错的证据**：10-18 22:52 群 827767299 那条“无@也回复”，发言者 QQ 是 **3614096161**，
   而**本实例机器人 QQ 是 3944860270（hesder）**；库中 3614096161 的 69 条消息
   100% 是 `type=user` 入站消息 ⇒ **那是群里另一个人/号，不是我们的机器人**
2. **全量排查（data_v4.db，10-17 起群消息）**：机器人“前一条消息没有 @ 它却发言”的
   记录**只有 4 条，且全是 `📰 每日早报`**（uapipro_toolbox 定时广播，配置 08:00，
   实际落在 09:52 / 13:03）⇒ **近期本实例没有真正的“主动聊天”行为**
3. **排除清单（均已证实）**：wake_enhance（窗口实际仅 20 秒 + 零日志）、
   followup（零条 `followup matched`）、active_reply（`enable=false`）、
   proactive_chat（**运行时被禁用**）、debounce（`enabled=false`）、
   qq_group_daily_analysis（白名单为空、incremental_trigger 不发送）

⇒ **“主动回复乱说话”目前没有证据支撑**；用户看到的“莫名其妙冒出来”
  更可能是**每日早报广播**（不基于上下文、时间不固定）。待用户指认具体场景后再定性。

## 重做时的设计要点（备忘，开工前再细化）
- **触发判定**：不看时间/概率，判断“此刻有没有值得说的”
  （有未被回答的问题 / 被提到 / 话题相关 / 冷场）；不该说话时闭嘴
- **上下文包**：最近 N 条对话 + **必须带图（多模态）** + 引用内容
- **防打扰**：冷却、同话题去重、别人正在回时不抢话、被 @ 时让位
- **可观测**：每次触发记录“为什么触发”，便于回看调参
- **协议**：自写、AGPL、署名清晰；独立仓库（放 extras），不碰他人代码

## 开工条件
用户安排在完成其他事项后、开新对话进行。本文档为交接依据。


---

# core 自带的记忆/历史能力盘点（2026-10-19 只读调研）

> 回答"我提到的记忆库是插件的还是 core 的"，以及"要不要自己造"。

## 归属澄清
| 之前提到的 | 真实归属 |
|---|---|
| `livingmemory` 727 条 memory_atoms | **外部插件**（astrbot_plugin_livingmemory） |
| `platform_message_history` 2279 条 | **core 自带**（`core/db/po.py:246`，内置星写入）✅ |

## core 能力清单
| 能力 | 持久化 | 保留策略 | 插件可调用 | 当前启用 |
|---|---|---|---|---|
| `platform_message_history` | ✅ SQLite | 每会话 **700 条滚动裁剪** | ✅ `context.message_history_manager` | ✅ |
| `conversations`（会话+checkpoint） | ✅ SQLite | **40 轮 + LLM 压缩**（老轮次原文丢失） | ✅ `context.conversation_manager` | ✅ |
| 知识库 RAG（FAISS） | ✅ | 手动管理 | ✅ `context.kb_manager.retrieve` | ❌ 全局 `kb_names=[]` |
| `provider_ltm_settings` | ❌ **内存 deque** | 1000 条，**重启即失** | ❌ 无接口 | group_icl=false |
| sp 会话 KV | ✅ | 手动 | ✅ `sp.session_put/get` | ✅ |
| `cron_manager` / `context.send_message` | ✅ | — | ✅ | 0 条任务 / 可用 |

⚠️ **`provider_ltm_settings` 名字像长期记忆，其实不是**：它只是群聊上下文注入（内存）+ 写历史表 + 概率主动回复，没有"总结成记忆"。

## 结论（用于主动回复插件）
- **可直接复用 core 的**：`send_message`(主动发且自动落历史)、`cron_manager`(定时触发)、
  `message_history_manager`(群流水 700 条)、`kb_manager`(语义检索)、sp KV(存自有状态)
- **core 没有、必须自建的**：**跨会话长程记忆**（总结 + 持久 + 重要度/衰减）。
  core 无任何"把对话总结成记忆并持久"的实现。
- `conversations` 会因 40 轮压缩丢失原文，**不能当长程记忆源**。

## 待验证（未测，不要当成结论）
1. livingmemory 的召回在"主动回复"这种非用户触发场景是否生效（它的 recall 挂在 `on_llm_request`）
2. enhance_mode 主动回复生成时会不会带上 livingmemory 的召回结果
⇒ 这两点决定"新插件复用 livingmemory 还是自建记忆层"，**必须实测**


---

# 魔改插件「主动回复判定」质量剖析（2026-10-19）

## 判定链路
入口 `main.py:2527 on_group_message` → `_allow_active_reply:986` → 攒栈 `2330`
→ `_judge_model_choice:2157`（7B 模型）→ 解析 `parse_proactive_decision:1918`
→ 本地二次否决 `_judge_local_skip_reason:1981`（**在模型调用之后**，`2295`）

## 已证实的设计缺陷
1. **人格正文被丢弃**：`2215-2218` 只取 `persona_name`，`persona_mask` 是硬编码占位
   "中性参考：简短、友好、有边界" ⇒ 判定器**不知道自己人设**
2. **攒栈消息丢弃**：`2222` 硬编码 `stack_size=1`，`model_stack_size` 配置形同虚设
3. **指代冲突**：机器人自发言在背景里写作 `You`（`3609`），与 system prompt 的"你"冲突
4. **顺序颠倒**：本地否决放在模型调用**之后**（`2295`），且与 `990` 重复执行 ⇒ 白跑一次 7B
5. **解析零容错**：恰好 4 key + ID 逐字相等 + reason 非空；7B 输出 ```json``` 围栏/数字 ID/
   多余字段 ⇒ 整体判否，且**不记录原文**（`2318` 只打"非标准输出按 SKIP"）⇒ 无法排障
6. **无 reason/raw 落盘** ⇒ 无法离线评估判定器质量
7. **本地正则过宽**：运维词（插件/配置/日志…）+ 常见动词（怎么/改/查…）即否决 ⇒ 吃正常闲聊
8. **节流叠加**：cooldown 120s + max_age 60s + batch 4~15s + quiet 900s

（注：判据并非没有——system_prompt `2260-2271` 给了 5 条优先级否决；但属"黑名单式"）

## 关键结论
- 近期"很少主动回复"的**首要原因是 `enable=false`**（日志窗口内判定 0 次）
- 若开启后仍很少，主因排序（把握度 70~80%，推测）：
  ① 解析零容错 ② 本地正则过宽 ③ 节流叠加 ④ 人格/攒栈信息缺失
- 日志关键字（用于实测）：`judge outcome`、`判定通过(REPLY)`、`判定拒绝(SKIP)`

## 离线回放思路（解决"没人用拿不到数据"）
用 `platform_message_history` 每群已有的 700 条真实历史，**离线**逐条喂给同一个判定
prompt（直接调 siliconflow 7B，不启机器人、不改配置），统计 REPLY/SKIP 命中率与 reason，
即可在没有群友参与的情况下评估判定质量并调 prompt。


---

# 主动回复判定：离线回放实测报告（2026-10-20）

脚本：`.workbuddy/proactive_judge_replay.py`（运行时自读密钥，不落盘；库只读；不改配置）
方法：取群 827767299 的 700 条真实历史，**剔除被 @ 机器人 / 唤醒前缀的消息**
（那些走正常回复路径，根本不进判定器），等距抽样 40 条，用插件**原样**的
system prompt（`main.py:2260-2271`）+ prompt 模板，分别喂 7B 与 DeepSeek。

## 结果
| 判定模型 | SKIP | REPLY | 出错/解析失败 |
|---|---|---|---|
| Qwen2.5-7B（**现用**） | 39 (98%) | **0 (0%)** | 1 (2%) |
| DeepSeek-V4.1-Flash | 39 (98%) | **1 (2%)** | 0 |

- DeepSeek 唯一 REPLY：`#5720「哦第二轮是镀金旅团」`（闲聊接话，理由合理）
- 疑似提问仅 1 条 `#5874「又要奶奶攻击?」`，两模型均 SKIP（短指代，合理）
- 7B 有一次 API 错误（5% 量级的不稳定）

## 结论（关键）
1. **"很少主动回复"有第二层原因**：不只是开关关着——**即便打开，判定也几乎永不触发**
2. 根因是**判定标准定位错了**：5 条否决 + 规则5 只在"明确求知识 / 可纠正错误 /
   有具体增量"才 REPLY ⇒ 这是**问答机器人**标准，不是**群友**标准
   ⇒ 真实群聊多为闲聊/图片/短句，于是几乎全部 SKIP
3. 也解释了早前的观察：7B 在**含 @ 的消息**上判 REPLY（把"被叫"当成"该主动说"）—
   说明它并没有真正理解"主动"的语义（该方法论错误已在脚本中修正）

## 对新插件的直接输入
- 判定不能是"是否值得回答"，应是"**此刻插话是否自然**"（社交时机，不是问题解答）
- 需要**影子模式**（只判定不发送 + 判定原文全量落盘）先跑准确率
- 判定与生成可分开模型；判定模型至少要能理解闲聊语境
