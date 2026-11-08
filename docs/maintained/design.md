# Design — AstrBot Maintained Fork

> 本文件回答「怎么做」。每个设计必须可追溯到 proposal 的某条需求。

## 1. 架构总览

```text
upstream AstrBotDevs/AstrBot (master)
        │  git fetch / 三方合并
        ▼
baseline/v4.29.4  (锚点 tag, = 3c7adafa)
        │
        ▼
maintained/v4.29.4  (长期主干)
        │
        ├── astrbot/api/**        ← 新增能力的唯一落点（插件可见）
        ├── astrbot/core/**       ← 仅已登记补丁，最小侵入
        └── maintained/           ← 台账、工具、版本（本 fork 自有，零冲突）
                │
                ▼
        插件（只允许 import astrbot.api.*）
```

## 2. 需求-方案对应关系表

| 需求ID | 需求描述 | 方案要点 | 落点文件 | 触碰对外可见路径 | 兼容影响 | 验证测试 |
|---|---|---|---|---|---|---|
| R-01 | 插件顶层 import 私有常量导致整体加载失败 | 在 `astrbot/api/**` 暴露该契约常量，插件改从 api 导入 | `astrbot/api/…` | 否（仅新增） | 无 | `tests/maintained/test_api_media.py` |
| R-02 | 函数内 import 私有 `direct_turns.coordinator` | api 层提供访问入口 + try/except 降级 | `astrbot/api/…` | 否 | 无 | `tests/maintained/test_api_turns.py` |
| R-03 | 在途 LLM 取消能力（需 `runner.request_stop`） | core 补丁 + api 层封装 | `astrbot/core/…` + `astrbot/api/…` | 否 | 无（默认关闭） | `tests/maintained/test_api_turns.py` |
| R-04 | 空参重复工具调用 14 次 | `REPEATED_TOOL_FAILURE_LIMIT` 补丁 | `astrbot/core/agent/runners/…` | 否 | 无 | 上游 `tests/test_tool_loop_agent_runner.py` |
| R-05 | provider 内部图片降级 | core 补丁 | `astrbot/core/provider/…` | 否 | 无 | `tests/maintained/test_api_media.py`、上游 `tests/test_process_stage_images.py` |
| R-06 | 维护保护（拦面板覆盖插件） | `star/maintenance.py` + `updater` 保护 | `astrbot/core/star/…` | 否 | 无 | 离线：`maintained/tools/check_drift.py` |
| R-07 | 补丁完整性可校验 | SHA-256 台账 + 比对脚本 | `maintained/installed_manifest.json` | 否 | 无 | `tests/maintained/test_manifest_guard.py` |

## 3. 兼容边界与冻结清单

### 3.1 冻结层（不可动）

- `astrbot/api/**` 现存**全部**符号。
- core 中被插件事实依赖的 5 个路径（视为事实公开，冻结）：
  - `astrbot.core.agent.message.TextPart`
  - `astrbot.core.provider.provider.EmbeddingProvider`
  - `astrbot.core.utils.astrbot_path.get_astrbot_data_path`
  - `astrbot.core.utils.io.download_image_by_url`
  - `astrbot.core.utils.quoted_message_parser.extract_quoted_message_images`

### 3.2 加法层（自由）

新模块、新钩子、新可选参数，**默认值必须保持旧行为**。

### 3.3 例外（内部重命名）

必须同时满足：shim 转发 + `DeprecationWarning` + 测试 + 单独提交并在 commit message 说明理由。

## 4. 新增模块清单（阶段 3 落 + 阶段 5 追加）

接口契约以 [`api-contract.md`](./api-contract.md) 为唯一规格（含签名、降级语义、测试要求）。

| 模块 | 职责 | 解决的共性问题 |
|---|---|---|
| `astrbot/api/_bridge.py` | 内部桥：惰性解析 core 符号 + 能力清单（非公开面） | 统一降级机制 |
| `astrbot/api/media/` | 图片输入契约与判定 | P1（插件顶层 import 私有常量）、P4（`<image_caption>` 硬编码） |
| `astrbot/api/turns/` | 直报回合状态访问与重置 | P2 的一半 |
| `astrbot/api/delivery/` | 交付策略纯函数 | P3 的一部分 |
| `astrbot/api/permissions/` | 权限与执行授权 | P6 |
| `astrbot/api/proactive/` | 轻量主动判定（开关恒关） | 铁律 6 |
| `astrbot/api/content/` | 内容部件类型 + `is_*` 判定 | 阶段 5 追加 |
| `astrbot/api/runtime/` | 运行时工具（数据目录 / 下载 / 引用图） | 阶段 5 追加 |
| `astrbot/api/embedding/` | 嵌入提供者类型 | 阶段 5 追加 |

**关键约束**：以上模块均为**新增文件**，**不修改**任何既有 api 文件（由 `tests/maintained/test_api_frozen.py` 守护）；
core 侧补丁在基线 4.29.4 上不存在，api 层必须降级可用、补丁就位后自动生效。

## 5. core 内部改动策略

最小侵入：新增文件 > 新增可选参数 > 修改函数体。**不删不改现有函数签名**。

## 6. 重命名与 shim 策略

```python
# 旧路径保留为 shim
def old_name(*args, **kwargs):
    warnings.warn("old_name is deprecated; use new_name", DeprecationWarning, stacklevel=2)
    return new_name(*args, **kwargs)
```

## 7. 关键调用链

1. **插件加载失败链路**：`main.py:28` 顶层 import → `astrbot.core.provider.entities` 缺符号 → 整个插件加载失败。修法：改从 `astrbot.api.*` 导入 + try/except。
2. **在途取消链路**：`direct_turns.coordinator` → `runner.request_stop` → 取消在途 LLM。修法：api 层封装 + 降级。

## 8. 降级方案（逐条兜底）

| 场景 | 兜底 |
|---|---|
| api 层符号缺失 | api 侧 try/except 回退内部实现或字面量常量，**插件加载永不失败** |
| 新钩子注册失败 | `logger.warning` 后跳过，主流程不受影响 |
| 新可选参数为 `None` | 走旧代码路径 |
| 主动回复相关异常 | 默认关闭（`proactive_must_remain_disabled` 恒 true） |
| 三方合并冲突 | 回退到 `baseline/v4.29.4`，按 `maintained/` 台账重放 |
| 台账 SHA 不匹配 | 比对脚本非零退出，阻断发布 |

## 9. 配置与开关设计

新开关一律**默认关闭 / 保持旧行为**；在 core 内新增，不修改既有配置项语义。

## 10. 测试策略

`tests/maintained/`；`ruff==0.15.22`；pytest；**阶段 4 起每个改动必带测试**。

## 11. 可观测性

日志前缀统一；`maintained/installed_manifest.json` 记录 SHA-256；`CHANGELOG.md` 记录变更。

## 12. 版本与发布策略

- **单一版本来源**：`astrbot/__init__.py` 的 `__version__`，形如 `4.29.4+mtn1`。
  `+mtnN` 后缀是 PEP 440 允许的本地版本标记，用于区分维护版与官方发布。
- `pyproject.toml` 的 `version` 保持基版本 `4.29.4`（不带后缀）：严格 `Version()` 调用方
  需要可解析的纯发布号。二者关系由 `tests/maintained/test_version_marker.py` 钉住。
- `maintained/VERSION` 是同一版本号的人类可读副本，必须与 `__version__` 完全一致，
  由 `test_version_marker.py` 校验；不是独立版本来源。
- 发布 tag：`maintained/v4.29.4-rN`（N 从 1 起）；阶段 7 转公开满足 AGPL §13。

## 13. 风险登记表

| ID | 风险 | 等级 | 缓解 | 触发阶段 |
|---|---|---|---|---|
| R1 | 存量 1639 行无测试、质量未知 | 🔴 | 阶段 2 逆向 + 阶段 3 补测试 | 2、3 |
| R2 | 第三方代码无许可证，公开分发违规 | 🔴 | 本仓库只发布 core 本体，第三方代码不进本仓 | 5 |
| R3 | 启动器持续覆盖 core | 🟠 | 台账 `--check` + 一键重打 | 4、6 |
| R4 | 多份状态脱节 | 🟠 | 单一真相源 + 同步哈希 | 全阶段 |
| R5 | 主动回复被误开启 | 🟡 | 铁律 6 + 降级默认关闭 | 3、4 |
| R6 | 上游 v4.29+ 语义不兼容 | 🟠 | 锁 v4.29.4，升级走三方合并 | 全阶段 |
