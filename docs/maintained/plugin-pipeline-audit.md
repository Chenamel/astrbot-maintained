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
2. 🔴 **`on_decorating_result` 四个插件改同一条消息链**
   （AtTool 转 At、splitter 分段、enhance_mode 改文本、meme_manager 替换）
   ⇒ **顺序敏感**：谁先谁后决定结果；某一方把另一方的标记切开就会失效
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
