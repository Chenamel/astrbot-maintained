# 拟人化架构方案：判定与生成分离

> 2026-10-22。目标只有一个：**让主动说出的话像人**。
> 本文档是方案，不是实现记录；动 core 之前需要拍板。

## 一、为什么现在不像人（有证据）

回放跑完 60 条 REPLY 草稿（31 条线上 + 29 条回放）后的结论：

- **信息量是过关的**：空草稿 0 条、纯情绪（红线）0 条
- **但全是"技术顾问/客服"口吻**：长、全、没有个人色彩

例子：

> 「PCL 可以用 HMCL 或直接下官方 launcher 做兜底；镜像没了还有 BMCLAPI 的镜像源和
> GitHub Release 直连。」

有信息，但不是人在群里说话的样子。

### 根因：persona 链根本没参与

扫了 17 个插件（只读），人格命中的分布是：

| 插件 | 人格/人设命中 | 挂载 |
|---|---|---|
| `self_learning` | **6494** | `on_llm_request` ×2 |
| `livingmemory` | 1031 | `on_llm_request` ×2 |
| `enhance_mode` | 126 | `on_llm_request` ×4 |

**人格的主宰是 self_learning，不是我们。** 而影子插件只挂了 `event_message_type`，
**完全不参与 `on_llm_request` / `on_llm_response`** —— 所以它写的草稿是裸的小模型输出，
结构上就不可能拟人。

这不是 prompt 调得不好的问题，是架构问题。

## 二、关键技术事实（决定了方案能不能做）

要让生成带上人格，就得让生成经过 `on_llm_request` 钩子。查了 core：

| 调用方式 | 是否触发 `on_llm_request` | 位置 |
|---|---|---|
| pipeline 的 agent runner | ✅ **是** | `pipeline/process_stage/method/agent_sub_stages/internal.py:403` |
| `context.llm_generate()` | ❌ 否（直接 `prov.text_chat`） | `star/context.py:196` |
| `context.tool_loop_agent()` | ❌ 否（同样直接调 provider） | `star/context.py:222` |

**结论：插件目前没有任何办法生成"带人格的话"。** 现有的两个 Context 方法都绕过人格链。

这正好是 fork 该补的东西 —— 项目定位写的就是「只补插件确实做不到的底层能力」。

## 三、三个方案

| 方案 | 做法 | 优点 | 代价 |
|---|---|---|---|
| **A（推荐）** | fork 在 `astrbot/api/` 新增一个**会走 `on_llm_request` 钩子的生成入口**，插件调它 | 自动获得 self_learning 人格 + livingmemory 记忆；不重复造轮子 | 要动 core：更新台账 SHA-256、补测试、走阶段门禁 |
| B | 插件构造内部事件，走 pipeline 生成 | 不用改 core | hack；会触发全部插件（splitter 分段、content_safety 等），副作用不可控 |
| C | 插件自己读 self_learning 的人格文本拼进 prompt | 不用改 core | 重复造轮子，且和 self_learning 的注入叠加或冲突 |

推荐 **A**。B 的副作用不可控，C 会和已经装的人格插件打架（这正是之前记录过的
"重叠比缺功能更危险"）。

### A 的设计草案

- 落点：`astrbot/api/`（遵循六铁律第 1 条：新增能力只落 api）
- 形态：`await api.proactive.generate(event, prompt, ...)` —— 内部构造一次
  `call_event_hook(event, EventType.OnLLMRequestEvent, req)`，然后才调 provider
- **默认关闭**，插件显式调用才生效，不影响任何原版行为
- 不动 `proactive_must_remain_disabled` 那套开关语义（六铁律第 6 条）

## 四、判定器该怎么改（配套）

判定与生成分离后，判定器不该再写草稿。它只回答"该不该说"：

```
{"decision":"REPLY"|"SKIP",
 "target":"针对哪条消息",
 "tone":"语气倾向",
 "needs_quote":是否引用,
 "needs_at":是否 @,
 "is_long_task":"我查查，稍后回你"这类,
 "reason":"一句话"}
```

草稿交给生成器。这样判定模型可以保持小而快，生成走有人格的主模型。

## 五、验收（怎么算"像人"）

1. **盲测**：把我们说的话和真人的话混在一起，能分辨吗 → 目标接近随机（50%）
2. **红线**：纯情绪附和占比 = **0**（用户最讨厌"豆包式"）
3. **不退化**：REPLY 率维持在 6% 上下，群友零投诉

第 2 条是硬约束：加了语气词却没有信息，比不说更招人烦。

## 六、待拍板

1. 走方案 A 吗？（要动 core，成本最大但最干净）
2. 若走 A：`astrbot/api/` 下新开模块，还是扩已有的 `api/proactive/`？
3. 生成器用哪个 provider？主模型（有人格）还是单独的？
