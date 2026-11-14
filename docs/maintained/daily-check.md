# 每日晨检（`daily_check.py`）

晨检的四项统计由 `maintained/tools/daily_check.py` 完成，自动化任务只负责将脚本输出原样呈现。统计口径以本文件为准；调整判据或阈值时，须同步更新代码、测试与本文档。

## 字段与数据源边界

日志、判定记录与数据库的字段口径存在以下边界，脚本已将这些规则固化：

- `shadow_log.jsonl` 中带有 `source=replay` 的回放记录不计入真实流量；
- `NO_JUDGE` 表示配额或节流跳过，不计入判定失败；
- 群号存放在 `group` 字段，形如 `default:GroupMessage:<id>`，`group_id` 恒为 `null`；
- `provider_stats.created_at` 为 UTC naive 时间戳，与本地日志时间相差 8 小时；
- 活跃日志位于 `core/data/logs/astrbot.log` 并按 `astrbot.<时间戳>.log` 轮转，统计时需扫描时间窗内全部轮转文件。

## 用法

```bash
python maintained/tools/daily_check.py --instance "<实例目录>"
python maintained/tools/daily_check.py --instance "<实例目录>" --date 2026-11-06
```

`--date` 省略时默认统计本地昨天；重点群通过 `--focus-group` 或环境变量 `ASTRBOT_FOCUS_GROUP` 指定，未指定时不摘录发送样本。
脚本为纯只读操作，不写实例文件、不重启服务。退出码仅表示脚本自身执行状态（`0` 成功 / `2` 参数或目录错误），健康等级直接体现在输出报告中。

## 四个数据源

| 用途 | 路径（相对 `<实例目录>`） | 时间字段 | 读取规则 |
|---|---|---|---|
| 错误与静默 | `core/data/logs/astrbot*.log` | 行首 `[YYYY-MM-DD HH:MM:SS.mmm]`（本地时间） | 扫描全部轮转文件，逐行按时间戳过滤，不按文件名过滤、不截断尾部行数 |
| 判定统计 | `core/data/plugins/*/shadow_log.jsonl` | `ts`（本地时间） | 逐行解析 JSON；跳过 `source=replay` 记录 |
| 真发送 | 同上 | 同上 | 仅统计 `sent=true`；重点群摘录 `persona_text` 前 60 字 |
| 成本 | `core/data/data_v4.db` 的 `provider_stats` 表 | `created_at`（**UTC naive**） | 统计 `token_input_other` 与请求数，按 `agent_type` 分组 |

## 时间窗

- 报告本地 GMT+8 的一个自然日，取半开区间 `[D 00:00, D+1 00:00)`。
- 数据库成本查询使用等价的 UTC 窗口 `[D-1 16:00, D 16:00)`。
- 窗口首尾两端同样计入静默时长计算，以检出全天无日志的停机状态；若统计日期为当天，则静默截止到当前时刻。

> 判定、日志与成本统计均统一对齐到本地自然日窗口。

## 健康分级

| 级别 | 触发条件 | 代码常量 |
|---|---|---|
| `incident`（⚠️ 异常） | 事故级错误 ≥ 1；窗口内零日志；最长静默 > 4 小时；判定 `ERROR` 占比 > 10% | `INCIDENT_GAP_MINUTES=240`、`ERROR_RATE_LIMIT=0.10` |
| `notice`（注意） | 最长静默 > 1 小时；噪声与其他错误合计 > 50 条 | `NOTICE_GAP_MINUTES=60`、`NOISE_LIMIT=50` |
| `ok`（通过） | 其余情况 | — |

仅 `incident` 级别标记 ⚠️。常见的外部网络与平台瞬态错误归入 `NOISE_RE` 单独计数，不触发异常：表情图/CDN 下载失败、@ 用户信息获取失败、上游 429/502/503/超时、asyncio 关闭异常，以及插件侧的 `ActionFailed`、接口错误码、内容安全审查失败、meme 图片解析失败、点赞/下载失败。
未命中任何规则的错误归入「其他」，并将前两条写入报告的「需关注」行，防止新型错误被静默忽略。

事故级错误以 `INCIDENT_RE` 为准：数据库损坏、`sqlite3.DatabaseError`、`PluginVersionUnsupportedError`、插件加载失败、`KeyError: 'items'`。

## 判定口径

- `NO_JUDGE` 为节流跳过，不计入失败；仅 `ERROR` 计入失败分子。
- `sent=true` 计为真实发送，`REPLY` 仅表示判定通过。
- 群 ID 取自 `group` 字段末尾段；`group` 为空的行不计入群排行。
- 失败率分母为窗口内全部判定行数（含 `NO_JUDGE`），防止节流放大失败率。

## 与自动化任务的契约

定时自动化任务仅运行本脚本并将不超过 8 行的输出原样贴出，不自行读取日志或数据库、不改写数值、不擅自增删异常标记。

## 与 `instance_check.py` 的分工

`maintained/tools/instance_check.py` 用于对单个插件执行重启后复核（需显式传入 `--plugin` 检查指定插件目录、配置与判定日志），不属于每日整体晨检流程。

## 维护约定

1. 调整事故/噪声正则、阈值或时间窗时，必须同步修改 `daily_check.py`、`tests/maintained/test_daily_check.py` 与本文档。
2. 报告输出严格控制在 8 行以内。
3. 脚本保持纯只读；修复实例文件请使用 `apply_patches.py`。
