# 插件能力发现契约（P2 处置 · T8-03）

> **目标**：core 不认识任何插件目录名。
> 判定方式是**能力契约**（插件暴露约定方法即拥有该能力），而不是按名字找插件。
>
> 决策时间：2026-10-11。守卫口径：**`astrbot/core/**` 内零插件目录名**（白名单为空）。

## 1. 背景：P2 问题

存量补丁里 core 硬编码了具体插件的目录名（实测 **2 处**，
非早期清单写的 3 处）：

| 位置 | 作用 |
|---|---|
| `astrbot/core/astr_main_agent.py` 的 `_is_lightweight_proactive_request` | 找到插件后调 `is_trusted_lightweight_proactive(event)` 判定轻量主动请求是否可信 |
| `astrbot/core/agent/runners/tool_loop_agent_runner.py` 的 `_finish_proactive_request` | 找到插件后调 `finish_proactive_request(event)` 做一次完成收尾 |

两处的**真实契约其实是方法名**（鸭子类型），目录名只是"怎么找到它"。
于是去掉名字只需改变**发现方式**，语义完全不变。

## 2. 处置：能力契约解析

**发现规则**（两处一致）：

1. 遍历 `star_registry`，要求 `metadata.activated` 且 `metadata.star_cls is not None`；
2. 用 `getattr(metadata.star_cls, <能力方法名>, None)` 取契约方法，**要求可调用**；
3. **首个命中者胜**（注册顺序），命中后不再继续扫描；
4. 调用抛异常 → 记 `logger.warning` 并 **fail-closed**（返回 False / 不收尾），绝不静默放行。

| 能力方法名 | 调用方 | 缺失时（fail-closed） |
|---|---|---|
| `is_trusted_lightweight_proactive(event)` | `_is_lightweight_proactive_request` | 返回 `False` ⇒ 按普通消息处理 |
| `finish_proactive_request(event)` | `_finish_proactive_request` | 不收尾（幂等标记仍置位，不重复尝试） |

### 为什么不建显式注册表

显式注册表（插件经 `astrbot.api.*` 声明能力、core 查询）更漂亮，但**要求插件侧同步改造**
并重新部署；在改造完成前功能会**先失效**。
能力契约法**零插件改动、行为逐点等价**，本轮即可闭环。
将来做「插件正规化重写」时再叠加注册表与 api 入口，本契约可作为其兜底发现方式。

## 3. 兼容性立场（与项目定位一致）

- 主动回复开关**不受影响**：本轮只改"如何找到可信校验器"，不碰任何开关语义；
  找不到 / 校验失败一律保持现有 fail-closed 结果。
- 任何第三方插件只要暴露同名方法即可参与；**不暴露则不参与**，不会误伤原版插件。

## 4. 守卫测试

`tests/maintained/test_plugin_capability_lookup.py` 含机械守卫：

- 正则 `(?<![\w])astrbot_plugin_[\w]+` 扫描 **`astrbot/core/**`**，命中即判红；
  （`(?<![\w])` 用于跳过 `get_astrbot_plugin_path` 这类路径辅助函数名）
- **范围限定 core**：`astrbot/api/web.py` 的 `astrbot_plugin_web_request` 是上游文件里的
  `ContextVar` 名，**不是插件目录名**，按零冲突原则不改上游文件，故不纳入扫描。

去掉名字后，新增/回归的插件耦合若再以目录名形式出现，会被该测试立刻拦下。
