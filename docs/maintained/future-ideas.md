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

## 与已装插件的分工（避免打架）

| 插件 | 职责 |
|---|---|
| `astrbot_plugin_astrbot_enhance_mode` | 群聊上下文 / Memory RAG / 主动回复 / 封禁 / WebUI |
| `astrbot_plugin_livingmemory` | 长期记忆 |
| `astrbot_plugin_splitter` | 分段发送 |
| `astrbot_plugin_wake_enhance` | 唤醒判定（正则、持续对话、白名单） |

fork 的新能力若与以上重叠，优先让插件做；fork 只补**底层缺口**。
