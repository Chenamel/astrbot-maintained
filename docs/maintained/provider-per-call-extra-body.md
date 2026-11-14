# Provider 单次请求附加参数使用说明

> 说明如何在单次调用 `Provider.text_chat` 或 `Context.llm_generate` 时通过 `extra_body` 传入仅对本次请求生效的底层 API 参数。

## 1. 背景与问题

上游 `provider_config.custom_extra_body` 属于 provider 实例级全局配置：一旦设置，该 provider 发出的所有请求都会附带相同参数。当同一 provider 同时服务于不同场景且参数诉求相反时（例如群聊主动回复的判定器需要设置 `reasoning.effort="none"` 关闭思考以降低延迟和 token 消耗，而主对话需要保持开启思考），配置级开关无法满足需求。

与此同时，在上游原生实现中，虽然 `Provider.text_chat(**kwargs)` 会将 `**kwargs` 传递给 `_prepare_chat_payload(..., **kwargs)`，但 `_prepare_chat_payload` 在组装 `payloads` 时仅提取固定字段，其余 `kwargs` 被直接丢弃。

## 2. 实现机制

在 `astrbot/core/provider/sources/openai_source.py` 与 `astrbot/core/provider/sources/openai_responses_source.py` 的 `_prepare_chat_payload` 返回前，合并调用方传入的 `extra_body` 字典：

```python
call_extra_body = kwargs.pop("extra_body", None)
if isinstance(call_extra_body, dict):
    payloads.update(call_extra_body)
```

下游 `_query` 方法会将 `payloads` 中不属于标准 `default_params` 的键自动归入底层 SDK 的 `extra_body` 发送给模型接口。由于合并在 `_prepare_chat_payload` 末尾执行，单次调用传入的 `extra_body` 可覆盖 provider 级默认同名字段，且作用域严格局限于当次请求。

## 3. 兼容性与容错

- **未传 `extra_body` 时行为不变**：`kwargs.pop("extra_body", None)` 返回 `None`，不修改 `payloads`。
- **非字典类型安全忽略**：若传入非 `dict` 值（如 `None` 或字符串），自动忽略且不抛异常。
- **测试覆盖**：`tests/maintained/test_provider_extra_body.py` 覆盖单次参数合并、覆盖默认字段及空值/非法值无副作用三项断言，同时通过上游 `tests/test_openai_source.py` 与 `tests/test_openai_responses_source.py` 全量测试。

## 4. 环境边界与降级表现

| 配置粒度 | 上游原版是否支持 | 作用范围 |
|---|---|---|
| `provider_config.custom_extra_body` | ✅ 原生支持 | 该 provider 的所有请求 |
| 单次调用传入 `extra_body={...}` | ❌ 仅维护分支支持 | 仅当次请求 |

在上游原版环境中，传入 `extra_body=` 不会报错，但会被 `_prepare_chat_payload` 静默丢弃（表现为参数未生效、模型仍按默认配置输出思考过程）。

## 5. 调用示例与实测效果

```python
await context.llm_generate(
    chat_provider_id="...",
    prompt=prompt,
    extra_body={"reasoning": {"effort": "none"}},
)
```

在判定器场景传入 `{"reasoning": {"effort": "none"}}` 的实测对比（200 条分层样本）：单次判定平均输出 token 从 461.5 降至 73.7（下降 84%），平均响应延迟从 4.42s 降至 1.92s，判定结果一致率保持在噪声范围内（73.0% vs 69.8%）。

## 6. 关联受保护文件

- `astrbot/core/provider/sources/openai_source.py`
- `astrbot/core/provider/sources/openai_responses_source.py`
