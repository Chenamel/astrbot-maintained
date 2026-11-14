# 维护分支特性与已知局限

> 本分支持续跟随 `baseline/*` 锚点指向的上游正式发布版本演进。
> 本文列出维护分支相对上游原版的核心差异、实测效果及维护代价。

## 0. 核心定位

上游解决「将大模型接入各聊天平台」的通用框架问题；本维护分支在不破坏上游插件兼容性的前提下，补充底层状态扩展 API、受保护文件漂移检测与主动回复人格链路支持。唯一硬约束是：**上游插件不改代码即可运行**。

## 1. 针对上游常见痛点的改进

| 上游常见痛点 | 维护分支的对应机制 |
|---|---|
| 插件直接依赖内部私有路径，核心升级后大面积失效 | 在 `astrbot/api/**` 提供带安全降级的公开扩展接口；改 core 须通过契约文档、测试常量与 `__all__` 三方同步门禁 |
| 核心补丁被启动器或升级操作静默覆盖后无从察觉 | `maintained/installed_manifest.json` SHA-256 台账 + `check_drift.py` 双端校验 + `apply_patches.py` 一键重放 |
| 主动发言或插件调模型时跳过请求钩子，丢失人设与记忆 | 提供 `api.proactive.generate_with_persona`，让生成请求先经过 `on_llm_request` 钩子链 |

## 2. 台账与漂移检测

- `maintained/installed_manifest.json`：逐条登记本分支修改或新增的所有 `astrbot/**` 文件及其磁盘字节 SHA-256 哈希，由 `tests/maintained/test_manifest_guard.py` 守护。
- `maintained/tools/check_drift.py`：支持仓库工作树与运行实例双端哈希比对，返回明确的退出码（`0` 无漂移 / `1` 有漂移 / `2` 环境错误）。
- `maintained/tools/apply_patches.py`：默认只读预演，传入 `--apply` 时先备份实例被覆盖文件再按台账写入并复核。
- `maintained/tools/sync_audit.py`：对比两个 `baseline/*` 标签之间的上游全量变更面，静态检查签名漂移、新增模块/依赖与前端资源同步情况。

## 3. 扩展 API 模块（`astrbot/api/**`）

所有扩展模块均落在 `astrbot/api/**` 下，底层 core 补丁未就位时自动返回安全默认值，不抛 `ImportError`：

| 公开模块 | 提供能力 |
|---|---|
| `api.turns` | 直发回合合并（文本与图片 URL）、当前回合判定与回合重置 |
| `api.delivery` | 代码任务识别与代码完整交付判定 |
| `api.permissions` | 管理员判定与单次消息执行意图授权判定 |
| `api.media` | 视觉输入可用性判定与图片转述失败防幻觉常量 |
| `api.content` | 文本与图片内容部件类型转发及安全判定函数 |
| `api.runtime` | 数据目录、远程图片下载、引用图提取、本地时间换算、完成钩子时序查询 |
| `api.embedding` | `EmbeddingProvider` 类型转发与判定 |
| `api.proactive` | 轻量主动场景判定、经过 `on_llm_request` 的人格生成与群历史写回 |
| `api.event.extras` | 9 个事件附加字段常量与带类型兜底的读写函数 |

### `generate_with_persona` 的作用机制

上游 `Context.llm_generate()` 与 `Context.tool_loop_agent()` 直接调用底层 provider，跳过了 `on_llm_request` 钩子，导致挂载在该钩子上的人格（`PERSONA_PLUGIN`）、长期记忆（`MEMORY_PLUGIN`）与群上下文（`CONTEXT_PLUGIN`）插件无法注入信息。`generate_with_persona` 先构造 `ProviderRequest`、写入机器人自身账号归属提示（`self_identity_note`），再触发 `on_llm_request` 钩子链，最后调用 provider 生成文本。

同一群聊上下文、同一模型下的实测输出对比：

> 经过钩子链：低金通解本来就是伪命题…看策划给不给环境，别追通解，追你手上拉满的那队就行
> 未经过钩子链：低金通解真没有，但这版本击破队盯着大丽花+阮梅走，生存位带加拉赫…

## 4. 权限、工具与运行时配置扩展

本分支新增的配置项默认均保持上游原版行为，按需在面板开启：

| 配置项 / 机制 | 说明 |
|---|---|
| `execution_gate_mode` | 默认 `legacy`（仅校验管理员身份，与上游一致）；设为 `strict` 时额外要求当前消息包含明确的运行/执行指令 |
| `hook_timing_mode` | 完成钩子触发时序；支持 `legacy`（回复先发出、钩子后执行）与 `enhanced`（钩子在回复发出前执行） |
| `direct_turn_quiet_sec` | `aiocqhttp` 同发送者连续消息聚合静默窗口（默认 4 秒，设为 0 关闭） |
| `lightweight_proactive_tools` | 非 @/唤醒的轻量主动回复允许保留的无副作用工具白名单（默认 29 项，支持与 `FunctionTool.is_lightweight_proactive_safe` 并集生效） |
| 单次请求 `extra_body` | `Provider.text_chat` 与 `Context.llm_generate` 支持传入仅对当次请求生效的 `extra_body` 字典（如为判定器单独关闭 `reasoning`） |

## 5. 质量门禁与发布规范

- 修改任何 `astrbot/**` 文件必须同步更新 `maintained/installed_manifest.json` 的 SHA-256，入库文件统一使用 LF 换行符。
- 发布前执行 `release_gate.py`，同时运行 `tests/maintained/` 维护测试集与上游全量 `tests/` 测试集；有意的上游测试偏差集中登记在 `maintained/p11_deviations.py` 并通过 `xfail(strict=True)` 守护。
- 本仓库只发布 core 本体，不包含任何插件。

## 6. 已知局限与维护代价

1. **跟进上游版本的合并成本**：每次同步上游新发布版本时，需要对台账登记的受保护文件执行三方合并，并通过 `sync_audit.py` 与全量测试门禁复核。
2. **上游配置 schema 断言偏差**：由于本分支在 `agent_runner.config.misc` 等位置新增了配置键，上游 2 项对配置字典做精确相等断言的测试会触发预期内偏差（已在 `maintained/p11_deviations.py` 登记为 `xfail(strict=True)`）。
3. **长钩子链下的人格位置稀释**：当实例同时安装十余个在 `on_llm_request` 中用 `+=` 追加 `system_prompt` 的插件时，前置写入的人格指令会被推挤到提示词中段；且高优先级外部防抖插件（如 `priority=100`）调用 `stop_event()` 会截断整条生成链，需配合 `retry_when_cancelled` 与 `hook_trace` 持续观测调优。

## 7. 常用校验命令

```bash
# 核对仓库工作树与台账 SHA-256（无需运行实例）
python -c "import hashlib,json,pathlib; f=json.load(open('maintained/installed_manifest.json',encoding='utf-8'))['files']; print('mismatch:', sum(hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()!=v for k,v in f.items()))"

# 仓库与运行实例双端漂移检测
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo

# 运行维护版测试套件与回放解析器自检
pytest tests/maintained -q
python maintained/proactive/replay.py --selftest
```
