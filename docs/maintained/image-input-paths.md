# 图片输入链路追踪（上游 4.28.2 vs fork）

状态：**只读追踪完成，未改动任何代码**
更新：2026-11-01 10:20（第一轮追踪 → 未知项清零）
方法：`fast-code-path`——从真实入口向上找写入者、向下追到 provider；结论按「已确认 / 可能 / 未验证」标注，未验证项必须写明缺口。
触发问题：群成员先发截图、26 秒后打字提问，主动回复看不到图，上下文里只有一个 `[Image]` 占位。

---

## 1. 范围

**追踪目标**：一条群消息里的 `Image` 组件，从抵达 → 落库 → 判定 → 生成 → 送进 provider，在哪一层被压缩、转述、丢弃或兜底。

**入口**
- 插件：`astrbot_plugin_proactive_shadow/main.py:1589` `on_group_message`
- core：`builtin_stars/astrbot/main.py:197` `on_message`、`:154` `persist_group_message`
- 请求出口：`proactive_persona.py:113`、`star/context.py:228`

**已检查**：`astr_main_agent.py`、`astr_main_agent_quote.py`、`proactive_persona.py`、`star/context.py`、`provider/entities.py`、`provider/manager.py`、`provider/sources/{openai,openai_responses,zhipu}_source.py`、`pipeline/scheduler.py`、`pipeline/.../agent_sub_stages/{image_input,internal}.py`、`utils/{media_utils,astrbot_path}.py`、`message/components.py`、`platform/sources/aiocqhttp/*`、`builtin_stars/astrbot/{main,group_chat_context}.py`、`dashboard/.../config-metadata.json`、插件 `main.py`、本实例 `cmd_config.json` 与插件配置文件。

---

## 2. 结论

全系统有 **三条** 走向 provider 的出口，只有第一条把图片当一等公民：

| 出口 | 压缩 | 模态判定 | 转述 | 不可用兜底 |
|---|---|---|---|---|
| `internal.py`（@ 唤醒） | ✅ 1280/q95 | ✅ | ✅ | ✅ |
| `star/context.py:228` `llm_generate` | ❌ | ❌ | ❌ | ❌ 纯透传 |
| `proactive_persona.py:113` `generate_with_persona` | ❌ | ❌ | ❌ | ❌ |

主动回复正好走了后两条：**判定拿到原图但没压缩，生成一张图都没拿到。**

本实例实测：判定与生成**是同一个云端模型** `deepseek-responses/deepseek-v4.1-flash`（`modalities` 声明含 `image`）。所以现在每次判定都在**把原图往云端传**，而真正要出话的生成阶段反而什么都没带。

---

## 3. 调用链

### 3.1 抵达与落库

| 步骤 | 代码位置 | 职责 | 输入→输出 | 副作用 | 确信度 |
|---|---|---|---|---|---|
| ① 入站转换 | `aiocqhttp_platform_adapter.py:306` `ComponentTypes[t](**m["data"])` | OneBot 段 → `Image(file=…, url=…)` | 段 → 组件（`file` 与 `url` 都可能有） | — | 已确认 |
| ② 群上下文开关 | `builtin_stars/astrbot/main.py:141` | `group_icl_enable or active_reply.enable` | — | — | 已确认 |
| ③ 群图转述 | `group_chat_context.py:206` | `Image` → 视觉模型 → `[Image: 描述]` | 组件 → 文本行 | 每图 1 次视觉调用 | 已确认（**本实例未执行**，见 §4.1） |
| ④ 落库 | `builtin_stars/astrbot/main.py:154` → `insert_message_chain` | 消息链 → 纯文本行 | `Image` → `{"type":"plain","text":"[image]"}` | 写 `platform_message_history` | 已确认 |

### 3.2 判定

| 步骤 | 代码位置 | 职责 | 输入→输出 | 副作用 | 确信度 |
|---|---|---|---|---|---|
| ⑤ 取引用 | 插件 `main.py:1718` `_judge_image_refs` | 本条消息的图；无则取同发送者 120s 内缓存 | 组件 → `url` 优先，本地文件转 data URI | 读内存缓存 | 已确认 |
| ⑥ 直调 | 插件 `main.py:1722-1726` | `llm_generate(image_urls=images)` | 原图，**无压缩** | 云端计费按原图 | 已确认 |
| ⑦ 透传 | `star/context.py:228` | → `prov.text_chat(image_urls=…)` | 无变换 | — | 已确认 |
| ⑧ 编码 | `provider/entities.py:264` → `resolve_image_ref_to_base64_data` | 仅物化 + 判 MIME | 原图 → data URL | docstring 明确「no conversion, no montage」 | 已确认 |

### 3.3 生成

| 步骤 | 代码位置 | 职责 | 输入→输出 | 副作用 | 确信度 |
|---|---|---|---|---|---|
| ⑨ 组装提示词 | 插件 `main.py:1802` → `_generate_persona(event, context_lines, verdict)` | **只收文本与判定结果** | 无图片入参 | — | 已确认 |
| ⑩ 发起 | 插件 `main.py:1169` `_persona_call` | 调 `generate_with_persona(...)`，**无 `image_urls`** | 图片在此消失 | — | 已确认 |
| ⑪ 建请求 | `proactive_persona.py:80` | `image_urls=list(image_urls or [])` = `[]` | — | — | 已确认 |
| ⑫ 插件钩子 | `proactive_persona.py:110` `call_event_hook` | 允许插件改 req | 可被 stop → 返回 None | debounce 在此掐断 | 已确认 |
| ⑬ 直连 provider | `proactive_persona.py:113` | `provider.text_chat(prompt, system_prompt, image_urls=req.image_urls, contexts)` | — | 跳过整条管线 | 已确认 |

### 3.4 @ 唤醒（正解对照）

| 步骤 | 代码位置 | 职责 | 确信度 |
|---|---|---|---|
| ⓐ 压缩+本地化 | `internal.py:344` → `image_input.py:17` → `prepare_model_image(1280, q95)` | 长边压到 1280、重写为本地路径 | 已确认 |
| ⓑ 引用图转述 | `internal.py:370` → `astr_main_agent_quote.py:152` | 能看就留、不能看才转述 | 已确认 |
| ⓒ 模态判定+转述 | `astr_main_agent.py:992-1007` → `_ensure_img_caption`（`:858`） | 判据 = `modalities` 含 `image`（空列表=全支持） | 已确认 |
| ⓓ 插件钩子 | `internal.py:402` | 同 ⑫ | 已确认 |
| ⓔ 钩子后重跑压缩 | `internal.py:412` | 接住插件在钩子里新加的图 | 已确认 |

---

## 4. 被这轮追踪推翻的三条旧结论

### 4.1 本实例上 core 并没有在转述群图片

`group_context_enabled()` 返回 `group_icl_enable or active_reply.enable`；本实例**两者皆 false** ⇒ `on_message` 在 `:199` 处早退，`group_chat_context.handle_message` 一次都没跑。

- ⇒ 「core 已在转述，我们再做一遍是重复付费」**错误**，它一次都没跑。插件自己转述**不存在重复成本**。
- ⇒ `[image]` 占位来自**另一条独立路径** `persist_group_message`（`:154`，受 `group_message_history_enable=true` 驱动）。

### 4.2 `IMAGE_INPUT_UNAVAILABLE_NOTICE` 不能用在主动回复里

`openai_source.py:158` `_context_has_unavailable_image` → `:1264` 命中即返回固定文案「当前看不到图片，请重新发送。」，**不调模型**；只查最后一条 user 消息的精确文本匹配。
本实例的生成 provider 是 `ProviderOpenAIResponses(ProviderOpenAIOfficial)`（`openai_responses_source.py:26`），**继承该短路**。

⇒ 主动路径若附这个常量，bot 会突然说「当前看不到图片，请重新发送。」，绕过人设。**兜底只能走 system_prompt 指令。**

### 4.3 两个「图片转述模型」是两套，有上游原文

`dashboard/.../config-metadata.json`：
- `:114` `provider_settings.default_image_caption_provider_id` →「图片转述模型」（本实例 `zhipu/glm-4.6v-flash`）
- `:1159` `provider_ltm_settings.image_caption_provider_id` →「群聊图片转述模型」，hint **「与图片转述模型分开配置」**（本实例 `openai/qwen3.5-9b-…`，未启用）
- `:1163` `group_message_history_enable` hint：**「媒体消息将保存为 [Image] 等占位文本」**

---

## 5. 未知项清零表

第一轮留下的每个「未验证 / 未展开」，逐条查完：

| # | 原未知项 | 查证方式 | 结果 |
|---|---|---|---|
| U1 | QQ 图片 URL 有效期 | 追 `aiocqhttp` 入站：`Image(file=…, url=…)` 由协议端给；插件 `_provider_ref` 优先取 `url` | **仍未验证**（需真实 CDN 链接才看得出签名有效期）。**但已规避**：缓存只活 120s，取用发生在毫秒级；不落盘、不跨重启 |
| U2 | 临时文件谁清理 | `astr_message_event.py:246` + `pipeline/scheduler.py:103` | 已确认：`finally: event.cleanup_temporary_local_files()`，在整条事件管线结束时统一清 |
| U3 | 主动回复是否在管线内 | 插件 `:1589` 普通 `@filter.event_message_type` 处理器，`await self._generate_persona(...)` 内联 | 已确认：在管线内 ⇒ U2 的清理对生成期文件同样生效 |
| U4 | `MediaResolver` 是否收 data URI | `media_utils.py:343/514/838` | 已确认：支持 本地路径 / `file://` / `http(s)` / `base64://` / `data:` / 裸 base64 |
| U5 | `prepare_request_images` 上游签名 | `diff <(git show baseline:…) <(…)` 签名段 | 已确认：逐字节一致 |
| U6 | 临时目录从哪来 | `utils/astrbot_path.py:75 get_astrbot_temp_path()` | 已确认：`<data>/temp` |
| U7 | 循环导入风险 | `grep proactive_persona` 全仓 | 已确认：只有 `api/proactive` 与 `api/_bridge` 用**字符串** resolve，core 内无 import ⇒ 可安全 import 其它 core 模块 |
| U8 | `extra_user_content_parts` 默认值 | `provider/entities.py:115` | 已确认：`field(default_factory=list)` |
| U9 | 判定/生成各用哪个模型 | 插件配置 + `provider/manager.py:50`（`agent_runner.config.model.provider_id`） | 已确认：判定 `deepseek-responses/deepseek-v4.1-flash`；生成 `persona_provider_id=""` → `curr_provider_inst` = **同一个** deepseek |
| U10 | Responses 源是否吃 `image_urls` | `openai_responses_source.py:237-267` `_prepare_chat_payload` → `assemble_context(prompt, image_urls, …)` | 已确认：透传，且有 `_materialize_context_image_parts` |
| U11 | `_generate_control` 是否会失真 | 本实例 `persona_control_enabled = false` | 已确认：当前不跑，风险只在将来开启时 |
| U12 | 插件实际 `max_images` | 本实例配置 | 已确认：`2`（非默认 3） |
| U13 | 其它 provider 源是否也短路 | `zhipu_source.py:10 ProviderZhipu(ProviderOpenAIOfficial)`；`siliconflow` 同族 | 已确认：均继承，行为一致 |
| U14 | 全仓库其余 agent runner 的图片路径 | 本实例 `runner_type=local`；coze/dify/deerflow 未启用 | 已确认：不参与，无需展开 |

**剩下唯一「未验证」是 U1**，且已由「不落盘、120 秒内取用」的设计规避。若将来要做跨重启缓存，必须先实测 CDN 链接有效期。

---

## 6. 附带上限（防止「发一堆图炸掉」）

| 项 | 当前值 | 来源 |
|---|---|---|
| 每群最近图组 | 3 张 | `_MAX_IMAGES_PER_GROUP` |
| 记住的群数 | 50 | `_MAX_IMAGE_GROUPS` |
| 图片记忆存活 | 120 s | `_IMAGE_TTL_SEC` |
| 每轮最多带图 | 2 | 实例配置 `max_images` |
| 内存最坏占用 | 50 × 3 × data URI ≈ 最高约 60 MB（**仅当图片以本地文件形式到达**；`url` 为 http 时不占） | 推算，非实测 |

---

## 7. 降级设计（修订）

`generate_with_persona` 内，`call_event_hook` 之后、`text_chat` 之前：

```
1) prepare_request_images(req, event, enabled, max_size, quality, output_dir, prepared)
   └─ 上游同名同签名；不存在则跳过 → 退化为原图直传
2) _provider_supports_modality(provider, "image")
   ├─ 真 → 送压缩后的本地文件（与 @ 唤醒完全一致）
   └─ 假 → 有 default_image_caption_provider_id 就 _ensure_img_caption 转述；没有则不加
3) 兜底：只在 system_prompt 追加「你看不到图，不要追问图里是什么」
   └─ 绝不使用 IMAGE_INPUT_UNAVAILABLE_NOTICE（会触发 provider 短路）
```

三层都可缺席，任一缺失都不让回复失败。参数全部读 `provider_settings`，与 @ 唤醒共用同一套旋钮。

---

## 8. 施工计划（未动工，待批准）

**阶段 A — core 接管线**（`astrbot/core/proactive_persona.py`，fork 自有，台账第 37 条）
- A1 钩子后插入第 1、2 步；`output_dir = Path(get_astrbot_temp_path())`，与 `internal.py:333` 同源
- A2 兜底走 system_prompt
- A3 台账 SHA-256 同步（key 用正斜杠）+ `tests/maintained/` 覆盖：能看图 / 不能看图但有转述 / 转述失败 / 全无
- A4 观测：日志出现压缩路径；同一张截图下主模型能复述图中文字

**阶段 B — 插件补参**（插件 `main.py`）
- B1 `_persona_call` 增 `image_urls`，取 `_judge_image_refs(event)`
- B2 `_generate_control`：本实例未启用，记一笔待将来同步，不阻塞

**阶段 C — 可选**
- C1 判定侧压缩（目前原图上传云端，是成本大头）
- C2 图片字节落盘 —— **前置条件：先实测 U1**

---

## 9. 回放样本盘点（2026-11-01 10:20 实测）

系统里有两套样本，**用途完全不同**，之前混为一谈：

| 样本 | 位置 | 规模 | 含图？ | 用途 |
|---|---|---|---|---|
| 判定回放结果 | `.workbuddy/proactive_replay_*.json` | 623 条（跨 42 群） | **0 条** | 纯文本判定回归基线 |
| 线上决策日志 | `<实例>/core/data/plugins/astrbot_plugin_proactive_shadow/shadow_log.jsonl` | **37,863 条**（25 MB） | `[Image]` 出现在 11,074 条的上下文中 | **图片路径的真实证据来源** |

字段：`ts / group / mode / current / context / images / elapsed_ms / raw / persona_text / sent / decision / reason`。

### 9.1 量化结果

| 指标 | 数值 |
|---|---|
| 总判定 | 37,863 |
| 上下文含 `[Image]` | 11,074（**29.3%**） |
| 判定时真的带上了图 | 152（**0.40%**） |
| REPLY 且图就在最近三条里、却一张没带 | **390** |
| 带图判定最终 SKIP（视觉成本白花） | 116 |

### 9.2 铁证样本（2026-11-01 08:51:12，群 1105248343）

```
#2 [久望故人归/00:50:46] [Image]          ← 图，同一发送者
#1 [久望故人归/00:51:05] 这个树叶提取器就是接不到电…
current: 同一句
images = 0                                  ← 一张没带
reply: …光凭描述定位不了，补个截图或者模组名吧   ← 让用户补一张他 19 秒前刚发过的图
```

### 9.3 实时观察的效果

10:15 起观察 100 秒：新增 28 条判定，命中该形状 **0 条**。
该形状占比约 1%，实时等命中效率极低 ⇒ **用历史样本，不要等实时**。

### 9.4 这批样本能做什么、不能做什么

- **能**：量化问题、做判定回归基线、验证「附上图后模型不再要求补图」。
- **不能**：逐条重放当时那张图。历史只存了 `[Image]` 占位，**没有 URL**（上游 `insert_message_chain` 天生 `path-free`）。
- ⇒ 真正的逐条复现，只能靠修好之后在生成侧记录图片引用，用**新样本**回放。

---

## 10. 待你决策（是产品选择，不是事实缺口）

1. 主动路径兜底那句话的具体措辞（进 system_prompt）。
2. C1 判定侧压缩：现在做，还是等 A 上线看日志再定。
3. `debounce.enabled` 仍为我取证时临时开的 `true`，是否恢复 `false`。

---

## 11. 落地结果（2026-11-01 12:30）

**已实现并部署**（两库各一提交，实例已重启，`check_drift` 双端 NO DRIFT）：

| 位置 | 改动 |
|---|---|
| `astrbot/core/proactive_persona.py` | 新增 `_prepare_images()`，在插件钩子之后、`text_chat` 之前执行三步：`prepare_request_images` 压缩本地化 → `_provider_supports_modality` 判定 → 不能看图则用 `_request_img_caption` 转述；都不能则清空 `image_urls` 并注入 `_NO_VISUAL_NOTE` |
| `astrbot_plugin_proactive_shadow/main.py` | 判定用的图片引用随 `_generate_persona` 传入 `generate_with_persona`，两次尝试都带（含被钩子掐断后的重试） |

**三个刻意的取舍**（写在这里，免得以后被"优化"掉）：

1. **不用 `_ensure_img_caption`**。它失败时会追加 `IMAGE_INPUT_UNAVAILABLE_NOTICE`，
   而 `openai_source._context_has_unavailable_image` 见到该文本会**短路、不调模型**，
   直接回「当前看不到图片，请重新发送。」—— 用户问图时说这句是合理的，bot 自己
   开口说这句就是事故。故改用底层 `_request_img_caption`，失败走 `_NO_VISUAL_NOTE`。
2. **`_NO_VISUAL_NOTE` 同时禁止两件事**：追问图片内容、以及描述图里有什么。
   只禁第一件会换来另一种破功（模型开始编造图的内容）。
3. **模态无法判定时保留图片**，而不是丢弃。core 对空 `modalities` 列表的解释是
   "全支持"，这里保持一致；丢弃才是静默回归。

**可观测**：每次带图的 REPLY 会留一条 INFO——`proactive image: sent to provider | count=N ...`
或 `proactive image: text only | captioned=True/False notice=...`。三档各计一次数，
观察脚本 `.workbuddy/observations/watch_quiet_window.py` 已在跑。

**尚未观察到的**：一次真实的「带图 REPLY」全链路。部署后群里还没有出现该形状，
需等采样累计。在拿到这条日志之前，只能说"代码路径已通、单测已过"，不能说"线上验证完成"。
