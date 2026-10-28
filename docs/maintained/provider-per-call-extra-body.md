# 逐次请求附加参数（per-call extra body）

> 登记项：`astrbot/core/provider/sources/openai_source.py`、
> `astrbot/core/provider/sources/openai_responses_source.py`
> 提交：`feat(provider): let a single call carry extra API fields`
> 动机来源：判定器需要关思考，主对话需要开思考，两者共用同一个 provider。

## 问题

`provider_config.custom_extra_body` 是**配置级**的：一旦填上，这个 provider 的
所有调用都会带上（上游原生行为）。当两个调用方对同一个参数需求相反时
（判定器要 `reasoning.effort=none`，主对话要默认思考），配置级开关无法表达。

插件侧也没法自己解决：`Provider.text_chat(**kwargs)` 把 `**kwargs` 一路传到
`_prepare_chat_payload(..., **kwargs)`，但该函数构造 `payloads` 时**只认固定字段**，
`kwargs` 到此为止被丢弃。

## 改动

在 `_prepare_chat_payload` 返回前合并调用方传入的 `extra_body`：

```python
call_extra_body = kwargs.pop("extra_body", None)
if isinstance(call_extra_body, dict):
    payloads.update(call_extra_body)
```

下游 `_query` 已有既定逻辑：`payloads` 中任何不在 `default_params` 的键会被移入
`extra_body` 发给 API。所以这里只需让键进得去。

合并放在最后，因此调用方可以覆盖默认字段（仅限本次请求）。

## 兼容性

- **不传 `extra_body` 时行为完全不变**：`kwargs.pop` 返回 `None`，`payloads` 不动。
- 传非 dict（例如字符串）时同样不生效，不会抛错。
- 上游测试：`tests/test_openai_responses_source.py`、`tests/test_openai_source.py`、
  `tests/unit/test_provider_stats.py`、`tests/test_provider_user_agent.py`
  共 **116 passed / 1 skipped**；`tests/` 全量上游套件通过（见部署记录）。
- 维护侧测试：`tests/maintained/test_provider_extra_body.py`（3 项）覆盖
  "会合并 / 可覆盖默认值 / 空值与非法值无副作用"。

## 边界（重要）

| 粒度 | 上游是否支持 | 影响范围 |
|---|---|---|
| `provider_config.custom_extra_body` | ✅ 原生 | 该 provider 的所有调用 |
| 单次调用 `extra_body=` | ❌ 仅本分支 | 仅本次请求 |

在上游实现里，`extra_body=` 会被 `_prepare_chat_payload` 静默丢弃——**不报错、只是
不生效**。因此任何依赖此能力的调用方（如 `astrbot_plugin_proactive_shadow` 的
`judge_extra_body`）在纯上游环境会表现为"填了没反应"，而不是报错。

这也是插件配置项 hint 里标注依赖的原因：**静默失败比报错更难排查**。

## 使用方式

```python
await context.llm_generate(
    chat_provider_id="...",
    prompt=prompt,
    extra_body={"reasoning": {"effort": "none"}},
)
```

已实测（`reasoning.effort=none`，qinglan 中转，deepseek-v4.1-flash）：输出 token
从 461.5 降到 73.7（-84%），延迟从 4.42s 降到 1.92s，与原判定一致率 73.0% vs 69.8%
（200 条分层样本，差异在噪声内）。

## 台账

`maintained/installed_manifest.json` 共 **52 条**；本次新增
`astrbot/core/provider/sources/openai_responses_source.py`
（`openai_source.py` 原已登记，仅同步哈希）。
