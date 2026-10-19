# 本机插件链路盘点（2026-10-18，只读）

> 目的：搞清楚 17 个插件分别在哪个阶段动手，找出**重叠与打架点**。
> 方法：静态扫描实例插件目录的钩子注册（`@filter.on_*`）与钩子体内的操作，
> 未改任何代码、未改任何配置。

## 一、请求链路与各阶段参与者

```text
1. 平台收到消息
      ↓
2. 唤醒判定           wake_enhance（正则 / 持续对话 / 白名单）+ 平台自身唤醒
      ↓
3. LLM 请求前  ★最挤  on_llm_request ×9
      ↓
4. LLM 生成 / 工具调用  AtTool(get_group_members)、enhance_mode(RAG 读写)、
      ↓                image_studio、meme_manager…
5. LLM 响应            on_llm_response ×6
      ↓
6. 装饰最终结果 ★易打架 on_decorating_result ×4
      ↓
7. 发送后 / 完成钩子    on_agent_done（content_safety_guard）
```

## 二、各阶段明细

| 阶段 | 插件 | 做了什么 |
|---|---|---|
| **on_llm_request** | `astrbot_plugin_astrbot_enhance_mode` | 改上下文文本（React 群聊上下文） |
| | `astrbot_plugin_livingmemory` | `handle_memory_recall`：查询并注入长期记忆 |
| | `astrbot_plugin_self_learning` | `inject_diversity_to_llm_request`：注入多样性 / 社交上下文 / 黑话 |
| | `astrbot_plugin_AtTool` | 注入系统提示（教模型输出 `[mention:ID]`） |
| | `astrbot_plugin_content_safety_guard` ×2 | 注入系统提示 + 改上下文，**可拦截** |
| | `astrbot_plugin_debounce` | **可拦截**（消息防抖/聚合） |
| | `astrbot_plugin_splitter` | 注入系统提示 |
| | `image_studio`、`meme_manager` | 各自能力注入 |
| **on_llm_response** | `enhance_mode` ×4、`content_safety_guard`、`debounce`、`livingmemory`、`splitter`、`meme_manager` | 改消息链 / 文本 / 系统提示 |
| **on_decorating_result** | `AtTool` | `[mention:ID]` → 真实 `At` 组件 |
| | `splitter` | 分段（改上下文 + 改消息链） |
| | `enhance_mode` | 改消息链 / 文本 |
| | `meme_manager` | 表情替换 |
| **on_agent_done** | `content_safety_guard` | 可拦截 |

## 三、冲突点（按风险排序）

1. 🔴 **三套记忆同时注入**（`enhance_mode` RAG + `livingmemory` + `self_learning`）
   ⇒ 上下文重复、口径可能互相矛盾，且**吃 token**
2. 🟢→🟡 **`on_decorating_result` 四个插件改同一条消息链**（2026-10-18 实测修订）
   - **已排除一个疑似冲突**：AtTool（转 `[mention:ID]` → 真 At，`main.py:296`）与
     enhance_mode（只解析**进来的** At，无输出构造）**方向相反，不冲突**
   - 实测：模型自主输出 mention 标签 → 蓝色真 At 组件 ✅（23:05:49，消息链
     `[引用消息][At:2494306515]`，对比历史回复无 At ⇒ 是模型动态加的，非自带）
   - 引用（`[引用消息]`）为**每条回复自带**
   - 剩余顺序敏感点：splitter 分段是否会把其他插件注入的组件切开（待群内长回复实测）
3. 🟡 **两个插件可拦截**（`content_safety_guard`、`debounce`）⇒ 拦截优先级不确定
4. 🟡 **`on_llm_request` 九个插件叠加注入** ⇒ 系统提示膨胀，可能挤掉人设/工具描述

> 注：钩子调用顺序取决于插件加载顺序（本轮日志未完整记录加载次序）。

## 四、建议（待用户定）

- **先观察**：跑一天，记录机器人表现不稳的具体场景（答非所问 / 记忆串味 / 分段错位），
  再对照上表定位是哪个插件造成的
- **可考虑精简**：三套记忆里挑 1–2 套主力（例如 `enhance_mode` RAG + `livingmemory`），
  避免同一份上下文被注入三次
- **fork 的定位不变**：只补**插件确实做不到**的底层能力（例如"让模型主动引用某条消息"，
  目前确实无人做，但单点价值需再评估）

## 五、配置调整记录

| 日期 | 插件 | 改动 | 原因 |
|---|---|---|---|
| 2026-10-18 | `livingmemory` | `recall_engine.top_k` **0 → 2** | 日志实证"top_k=0 <= 0，跳过记忆召回" ⇒ 长期记忆**只存不取**。改后日志走到 `memory_recall:237/301`，召回生效 |

> 影响：每条消息多一次 Embedding 调用（siliconflow）+ 上下文注入约 2 条记忆。
> 备份：`.workbuddy/livingmemory_config.backup-*.json`


## 六、主动回复触发源调查（2026-10-19，为重写做准备）

用户反馈"群友觉得不聪明"的**真因是主动回复**：莫名其妙冒出来说话、不带上下文、
开口没信息量、图片被忽略。查配置得到的触发源清单：

| 候选 | 配置 | 状态 | 判断 |
|---|---|---|---|
| `enhance_mode.active_reply` | `enable: false` | **关** | 不是它 |
| `enhance_mode.followup` | `{enable: true, window_sec: 300}` | **开** | ⚠️ 5 分钟窗口内会追加回复 |
| `wake_enhance.continuous_awakening` | `{enable: true, waking_interval: 20}` | **开** | ⚠️ 唤醒后 20 分钟内免 @ 持续响应 |
| `proactive_chat` | `auto_trigger: false` | 半关 | 不自动触发 |

⇒ "莫名其妙冒出来"多半来自 **followup + 持续唤醒**，而不是专门的主动回复功能。
重写前必须先把这两条的实际行为审计清楚（谁在发、上下文里有什么、图有没有带上）。

### 待办（新对话开工前先做）
1. 关掉 followup / 持续唤醒各试一天，确认哪个是主因
2. 抓一次真实"主动回复"的完整日志，看上下文里**有没有图片**
   （群历史转述配置 `group_history_enhancement.image_caption=true`，但主动链路是否带图未验证）
3. 确认现有魔改插件的许可证状况（决定能否参考/重写）

