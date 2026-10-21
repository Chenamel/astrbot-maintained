# proactive/ — 主动回复项目的离线工具区

本目录是「主动回复」项目的**文档与离线工具**区，和 `maintained/tools/` 职责不同，
边界如下（避免和 fork 的既有约定打架）：

| 约定 | 本目录是否适用 |
|---|---|
| 只登记 core 台账（`installed_manifest.json`） | ❌ 不参与，本目录不进台账、不参与漂移检测 |
| `maintained/tools/` 不碰实例数据/插件 | ⚠️ 本目录**例外**：它就是为实例里的影子插件服务的，只读实例库 + 配置 |
| 随 fork 发布到线上 | ❌ 不部署，只在开发机上跑 |
| 改动 `astrbot/**` | ❌ 不改任何 core 文件 |

## 内容

| 文件 | 用途 |
|---|---|
| `scenarios.py` | 手工构造的极端场景语料（合并转发/语音/刷屏拆句/话题并行/双机器人/撤回/闭嘴/注入/长代码贴） |
| `replay.py` | 回放驱动：把历史库真实消息重放成合成群消息事件，触发影子插件的 `on_group_message` |

## 跑法

```bash
# 零成本冒烟（不调模型，验证链路）
PYTHONPATH=<仓库根> <实例>/venv/Scripts/python.exe maintained/proactive/replay.py \
    --dry-run --sample 12

# 正式回放（约 500 次判定，10~25 分钟）
PYTHONPATH=<仓库根> <实例>/venv/Scripts/python.exe maintained/proactive/replay.py \
    --sample 500
```

## 哪些是真的，哪些是装配出来的

回放的目的是**让插件自己的代码被真正执行**，而不是绕过去直接问模型。因此：

**真**：

- 插件模块从实例目录加载，跑的是它自己的 `on_group_message`（含读历史、读图、
  JSON 解析、写日志）
- `astrbot.core.star.Context` 是 core 的类，`llm_generate` 就是 core 的那个方法
- 判定模型 provider 由 core 的工厂逻辑（`ProviderManager` 的配置合并 →
  `provider_cls_map` → `cls_type(config, settings)`）造出来，与线上同类同配置
- `PlatformMessageHistoryManager` + 真实 SQLite，查的是真实历史行

**装配**：

- 事件对象用 `AstrMessageEvent` 子类而非 aiocqhttp 的事件类（插件只用到基类方法）
- provider manager 只认识判定用的那一个 provider（`llm_generate` 只用它）
- 上下文窗口：生产里入站消息先落库（`builtin_stars/astrbot/main.py`，
  priority `maxsize - 2`），所以被判定的那条**本身就在历史末尾**；回放用一个
  只读备份出来的临时库按 id 裁剪，还原同样的窗口

**安全**：

- 语料库以 `mode=ro` 打开并用 `sqlite3` backup 复制，实例库不被写入、不被锁
- 插件 `mode=shadow`，回放也不调用任何发送接口
- 判定结果默认追加到插件的 `shadow_log.jsonl`，带 `source=replay` / `run_id` /
  `scenario` 标记，可用 `.workbuddy/shadow_report.py` 按来源筛选
