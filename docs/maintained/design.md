# Design — AstrBot Maintained Fork

> 本文件回答「怎么做」。每个设计必须可追溯到 proposal 的某条需求。

## 1. 架构总览

```
upstream AstrBotDevs/AstrBot (master)
        │  git fetch / 三方合并
        ▼
baseline/v4.28.2  (锚点 tag, = 3c7adafa)
        │
        ▼
maintained/v4.28.2  (长期主干)
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
| R-01 | 插件顶层 import 私有常量导致整体加载失败 | 在 `astrbot/api/**` 暴露该契约常量，插件改从 api 导入 | `astrbot/api/…` | 否（仅新增） | 无 | `tests/maintained/test_api_surface.py` |
| R-02 | 函数内 import 私有 `direct_turns.coordinator` | api 层提供访问入口 + try/except 降级 | `astrbot/api/…` | 否 | 无 | 同上 |
| R-03 | 在途 LLM 取消能力（需 `runner.request_stop`） | core 补丁 + api 层封装 | `astrbot/core/…` + `astrbot/api/…` | 否 | 无（默认关闭） | `tests/maintained/test_turns.py` |
| R-04 | 空参重复工具调用 14 次 | `REPEATED_TOOL_FAILURE_LIMIT` 补丁 | `astrbot/core/agent/runners/…` | 否 | 无 | `tests/maintained/test_tool_loop.py` |
| R-05 | provider 内部图片降级 / QQ 图片本地化 | core 补丁 | `astrbot/core/provider/…`、`astrbot/core/platform/…` | 否 | 无 | `tests/maintained/test_media.py` |
| R-06 | 维护保护（拦启动器覆盖） | `star/maintenance.py` + `updater` 保护 | `astrbot/core/star/…` | 否 | 无 | `tests/maintained/test_maintenance.py` |
| R-07 | 补丁完整性可校验 | SHA-256 台账 + 比对脚本 | `maintained/installed_manifest.json` | 否 | 无 | 台账比对 |

## 3. 兼容边界与冻结清单

### 3.1 冻结层（不可动）

- `astrbot/api/**` 现存**全部**符号。
- core 中被插件**事实依赖**的 5 个路径（视为事实公开，冻结）：
  - `astrbot.core.agent.message.TextPart`
  - `astrbot.core.provider.provider.EmbeddingProvider`
  - `astrbot.core.utils.astrbot_path.get_astrbot_data_path`
  - `astrbot.core.utils.io.download_image_by_url`
  - `astrbot.core.utils.quoted_message_parser.extract_quoted_message_images`

### 3.2 加法层（自由）

新模块、新钩子、新可选参数 —— **默认值必须保持旧行为**。

### 3.3 例外（内部重命名）

必须同时满足：shim 转发 + `DeprecationWarning` + 测试 + **单独提交**并在 commit message 说明理由。

## 4. 新增模块清单（阶段 3 落）

| 模块 | 职责 | 对外符号 | 是否 api 层 |
|---|---|---|---|
| `astrbot/api/turns` | 直连会话轮次与在途取消 | 待定 | 是 |
| `astrbot/api/media` | 图片/媒体输入降级与本地化 | 待定 | 是 |
| `astrbot/api/delivery` | 代码交付策略 | 待定 | 是 |
| `astrbot/api/permissions` | 执行权限闸门 | 待定 | 是 |
| `astrbot/api/proactive` | 主动场景工具白名单 | 待定 | 是（默认关闭） |

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
| 三方合并冲突 | 回退到 `baseline/v4.28.2`，按 `maintained/` 台账重放 |
| 台账 SHA 不匹配 | 比对脚本非零退出，阻断发布 |

## 9. 配置与开关设计

新开关一律**默认关闭 / 保持旧行为**；在 core 内新增，不修改既有配置项语义。

## 10. 测试策略

`tests/maintained/`；`ruff==0.15.22`；pytest；**阶段 4 起每个改动必带测试**。

## 11. 可观测性

日志前缀统一；`maintained/installed_manifest.json` 记录 SHA-256；`CHANGELOG.md` 记录变更。

## 12. 版本与发布策略

- `pyproject.toml` 与 `astrbot.__version__` **保持 4.28.2 不变**（减少三方合并冲突）。
- 本 fork 版本记在 `maintained/VERSION`（如 `4.28.2.m1`）与 `CHANGELOG.md`。
- 发布 tag：`maintained/v4.28.2-rN`（N 从 1 起）；阶段 7 转公开满足 AGPL §13。

## 13. 风险登记表

| ID | 风险 | 等级 | 缓解 | 触发阶段 |
|---|---|---|---|---|
| R1 | 存量 1639 行无测试、质量未知 | 🔴 | 阶段 2 逆向 + 阶段 3 补测试 | 2、3 |
| R2 | 插件无许可证，公开分发违规 | 🔴 | 改动全部进私有仓 `astrbot-extras` | 5 |
| R3 | 启动器持续覆盖 core | 🟠 | 台账 `--check` + 一键重打 | 4、6 |
| R4 | 多份状态脱节 | 🟠 | 单一真相源 + 同步哈希 | 全阶段 |
| R5 | 主动回复被误开启 | 🟡 | 铁律 6 + 降级默认关闭 | 3、4 |
| R6 | 上游 v4.29+ 语义不兼容 | 🟠 | 锁 v4.28.2，升级走三方合并 | 全阶段 |
