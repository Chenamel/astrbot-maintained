# 每日晨检（daily_check.py）

晨检的四项统计由 `maintained/tools/daily_check.py` 完成，自动化任务只负责把输出
**原样呈现**。口径以本文件为准：改判据时，代码、测试和本文必须一起改，
否则下次又会出现"每天异常但没人知道在报什么"。

## 为什么交给脚本

早期晨检是让模型每天现读日志、JSONL 和 SQLite 再自己汇总，于是反复出现口径漂移：

- `shadow_log` 一度有 `source=replay`，后来字段消失，"排除 replay"这步失效；
- `NO_JUDGE` 是节流（`skipped_by=quota/throttle`），曾被误当成失败；
- 群 ID 在 `group` 字段（`default:GroupMessage:<id>`），`group_id` 恒为 null；
- `provider_stats.created_at` 是 UTC naive，和日志/判定的本地时间差 8 小时；
- 活跃日志在 `core/data/logs/astrbot.log`，不在实例根目录；日志会轮转成
  `astrbot.<时间戳>.log`，只看当前文件的末 4000 行会连着漏报；
- `--since` 只有下界，把执行日当天的错误算进了"昨天"。

这些都不该由模型每次重新推断。脚本把时间窗、字段、分类固定下来，模型只读结果。

## 用法

```bash
python maintained/tools/daily_check.py --instance "<实例目录>"
python maintained/tools/daily_check.py --instance "<实例目录>" --date 2026-11-06
```

`--date` 省略时取本地昨天；`--focus-group` 可换重点群（默认 `1105248343`）。
**只读**：不写实例、不重启服务。退出码只表示脚本能否运行（0 成功 / 2 目录不对），
**不表示健康等级** —— 有事也在报告里说，不用退出码报警。

## 四个数据源

| 用途 | 路径（相对实例根） | 时间字段 | 注意 |
|---|---|---|---|
| 错误与静默 | `core/data/logs/astrbot*.log` | 行首 `[YYYY-MM-DD HH:MM:SS.mmm]`，本地 | 扫全部轮转文件，逐行按时间戳过滤，不按文件名、不截断末 4000 行 |
| 判定统计 | `core/data/plugins/astrbot_plugin_proactive_shadow/shadow_log.jsonl` | `ts`，本地 | 每行一个 JSON；`source=replay` 跳过（兼容旧文件） |
| 真发送 | 同上 | 同上 | 仅 `sent=true` 计入；重点群摘录 `persona_text` 前 60 字 |
| 成本 | `core/data/data_v4.db` 的 `provider_stats` | `created_at`，**UTC naive** | 只统计 `token_input_other` 与请求数；按 `agent_type` 分组 |

## 时间窗

- 报告本地 GMT+8 的一个自然日，半开区间 `[D 00:00, D+1 00:00)`。
- 成本表用等价的 UTC 窗口 `[D-1 16:00, D 16:00)`，避免把 UTC 日期当成本地日期。
- 日志行不满足窗口就丢弃；窗口两端也计入静默时长，所以"全天无日志"能被发现。
- 若报告日就是今天，静默只算到当前时刻——**尚未到来的时间不算停机**。

> **口径修正（2026-11-07）**：此前的晨检记录把「UTC 日历日」当成「昨天」。
> 例如 11-06 记成 1118 请求 / 258.4 万 input_other，按本地日等价窗口实际是
> **1023 请求 / 222.0 万**。旧数字混了 8 小时时区，不要用历史记录里的成本数
> 校验本脚本；判定、日志、成本的窗口现在完全一致。

## 健康分级

| 级别 | 触发条件 | 代码常量 |
|---|---|---|
| `incident`（⚠️ 异常） | 事故级错误 ≥1；窗口内零日志；最长静默 > 4 小时；判定 ERROR 占比 > 10% | `INCIDENT_GAP_MINUTES=240`、`ERROR_RATE_LIMIT=0.10` |
| `notice`（注意） | 最长静默 > 1 小时；噪声与其他错误合计 > 50 条 | `NOTICE_GAP_MINUTES=60`、`NOISE_LIMIT=50` |
| `ok`（通过） | 其余 | — |

**只有 `incident` 才加 ⚠️。** 日常外部噪声单独计数，不再触发异常：表情图/CDN
下载失败、@ 用户信息获取失败、上游 429/502/503/超时、asyncio 关闭异常，
以及插件侧的 `ActionFailed`、接口返回错误代码、内容安全 LLM 审查失败、
meme 图片解析失败、点赞/下载失败。这些都是执行记录里反复出现、无需每日
追查的老面孔；`NOISE_RE` 是它们的唯一清单。
未被任何规则匹配的错误归入"其他"，并把前两条塞进报告的「需关注」行 ——
新类型的错误不会被静默吞掉，维护者据此决定要不要加进事故或噪声清单。

事故级关键词以 `INCIDENT_RE` 为准：数据库损坏 / `sqlite3.DatabaseError` /
`PluginVersionUnsupportedError` / 插件加载失败 / `KeyError: 'items'`。

## 判定口径

- `NO_JUDGE` 是节流，**不算失败**；只有 `ERROR` 计入失败率。
- `sent=true` 才是真发送，`REPLY` 只表示判定结果。
- 群 ID 取自 `group` 字段最后一段；`group` 为空的行不计入群排行。
- 失败率分母是窗口内全部判定（含 `NO_JUDGE`），这样占比不会被节流放大。

## 与自动化任务的契约

「Hesder 每日晨检」（每天 09:00）只做一件事：运行脚本，把不超过 8 行的输出
原样贴出。它**不自行读日志或数据库、不改写数字、不自行加异常标记**。
需要人话解读时可以补一句，但不得改动报告里的数值与级别。

## 与 instance_check.py 的分工

`maintained/tools/instance_check.py` 是给**单个插件做重启复核**的只读工具
（检查该插件目录、配置与判定日志）。它不是整体健康检查，晨检不再依赖它；
要用它请显式传 `--plugin`，否则插件相关检查会跳过而不是报红。

## 维护约定

1. 新增事故/噪声类型、改阈值、改时间窗：同时改 `daily_check.py`、
   `tests/maintained/test_daily_check.py` 和本文，一笔提交。
2. 输出行数上限 8 行，自动化按这个上限排版。
3. 脚本不写任何实例文件；需要修实例数据时走 `apply_patches.py`。
