# 架构分层与兼容边界说明

> 本文件说明维护分支的目录分层、兼容冻结边界、内部转发机制与版本发布规则。

## 1. 架构总览

```text
upstream AstrBotDevs/AstrBot (master)
        │  git fetch / 三方合并
        ▼
baseline/*  (附注标签锚点，指向当前同步的上游正式发布提交)
        │
        ▼
maintained/*  (长期维护主干)
        │
        ├── astrbot/api/**        ← 扩展 API 的唯一公开落点（插件可见）
        ├── astrbot/core/**       ← 最小侵入式补丁（全部登记 SHA-256 台账）
        └── maintained/           ← 台账、运维工具、版本与基线记录（与上游零路径冲突）
                │
                ▼
        外部插件（仅依赖 astrbot.api.*）
```

## 2. 核心设计目标与落点映射

| 领域 | 解决的问题 | 方案要点 | 落点路径 | 验证测试 |
|---|---|---|---|---|
| 媒体契约公开化 | 插件顶层导入 core 私有常量在核心升级后触发 `ImportError` | 在 `astrbot/api/media` 暴露常量与判定函数，缺失时镜像兜底 | `astrbot/api/media/` | `tests/maintained/test_api_media.py` |
| 直发回合协调 | 同一用户连续发言合并与在途请求过期判定 | `direct_turns` 协调器 + `astrbot/api/turns` 只读/重置封装 | `astrbot/core/utils/direct_turns.py`、`astrbot/api/turns/` | `tests/maintained/test_api_turns.py` |
| 工具循环防死锁 | 模型空参或重复调用同一失败工具导致死循环 | `REPEATED_TOOL_FAILURE_LIMIT` 阈值拦截 | `astrbot/core/agent/runners/` | `tests/test_tool_loop_agent_runner.py` |
| 图片输入降级防幻觉 | 图片转述失败时模型凭上下文盲猜图片内容 | 注入 `IMAGE_INPUT_UNAVAILABLE_NOTICE` 防幻觉指令 | `astrbot/core/provider/`、`astrbot/core/pipeline/` | `tests/maintained/test_api_media.py` |
| 本地维护插件保护 | 面板误更新或误卸载本地维护版插件 | `star/maintenance.py` 检查保护名单，损坏时 fail-closed | `astrbot/core/star/maintenance.py` | `tests/maintained/test_maintenance_gate.py` |
| 受保护文件完整性 | 启动器或外部操作覆盖 core 补丁后静默失效 | `installed_manifest.json` SHA-256 台账 + `check_drift.py` | `maintained/installed_manifest.json` | `tests/maintained/test_manifest_guard.py` |

## 3. 兼容边界与冻结清单

### 3.1 冻结层（严禁破坏签名或删除）

- 上游 `astrbot/api/**` 现存的全部模块与导出符号（由 `tests/maintained/test_api_frozen.py` 守护）。
- `astrbot/core/**` 中被社区插件广泛使用的 5 个事实公开符号（已同步通过 `astrbot/api/` 转发，原路径保持冻结）：
  - `astrbot.core.agent.message.TextPart`（含配对的 `ImageURLPart`）
  - `astrbot.core.provider.provider.EmbeddingProvider`
  - `astrbot.core.utils.astrbot_path.get_astrbot_data_path`
  - `astrbot.core.utils.io.download_image_by_url`
  - `astrbot.core.utils.quoted_message_parser.extract_quoted_message_images`
- `astrbot/core/tools/computer_tools/util.py` 中的 `check_admin_permission`（保留在 `__all__` 中作为身份级权限转发器，兼容上游 monkeypatch 测试）。

### 3.2 扩展层（只做加法）

新增 API 模块、新增可选参数与新增配置项的默认值必须保持与上游原版一致的行为，确保未修改配置的实例与原版插件零感知运行。

### 3.3 内部重命名与 shim 规范

若确需重命名内部函数，必须在原路径保留 shim 转发函数、发出 `DeprecationWarning` 并附带回归测试：

```python
def old_name(*args, **kwargs):
    warnings.warn("old_name is deprecated; use new_name", DeprecationWarning, stacklevel=2)
    return new_name(*args, **kwargs)
```

## 4. 扩展 API 模块清单

详细签名与降级规格见 [`api-contract.md`](./api-contract.md)。

| 模块路径 | 核心职责 |
|---|---|
| `astrbot/api/_bridge.py` | 内部桥接：惰性解析 core 符号与 `capabilities()` 状态汇总（非公开面） |
| `astrbot/api/media/` | 图片输入可用性判定与防幻觉提示常量 |
| `astrbot/api/turns/` | 直发回合合并文本/图片查询、已发送标记与会话回合重置 |
| `astrbot/api/delivery/` | 代码任务识别与代码完整交付判定 |
| `astrbot/api/permissions/` | 管理员身份校验与单次执行意图授权判定 |
| `astrbot/api/proactive/` | 轻量主动场景判定、经过 `on_llm_request` 的人格生成与历史写回 |
| `astrbot/api/content/` | 文本与图片内容部件类型转发及安全类型判定函数 |
| `astrbot/api/runtime/` | 数据目录、图片下载、引用图提取、本地时间格式化与钩子时序查询 |
| `astrbot/api/embedding/` | `EmbeddingProvider` 类型转发与判定 |
| `astrbot/api/event/extras.py` | 事件附加字段键名常量与带类型兜底的读写函数 |

## 5. core 内部改动准则

遵循最小侵入原则：优先新增独立文件，其次新增带默认值的可选参数，最后才修改既有函数体。严禁删除或缩窄既有公开及半公开函数的参数签名。修改任何 `astrbot/**` 文件后必须同步更新 `maintained/installed_manifest.json` 的 SHA-256。

## 6. 異常与降级兜底策略

| 场景 | 降级行为 |
|---|---|
| 底层 core 补丁模块缺失 | `astrbot/api/*` 经 `_bridge.resolve` 返回安全默认值，插件正常加载不抛 `ImportError` |
| 事件附加字段类型不符或缺失 | `astrbot/api/event/extras.py` 读取器返回对应类型的空默认值并记 debug 日志 |
| 新增可选参数未传或为 `None` | 完全走上游原有代码路径 |
| 三方合并出现冲突或漂移 | 以当前 `baseline/*` 锚点标签与 `maintained/installed_manifest.json` 为参照执行 `sync_audit.py` 与 `check_drift.py` |
| 台账 SHA-256 校验不匹配 | `test_manifest_guard.py` 与 `release_gate.py` 报错阻断发布 |

## 7. 版本号与发布规则

- **版本字符串三处严格一致**：`pyproject.toml` 的 `version`、`astrbot/__init__.py` 的 `__version__` 与 `maintained/VERSION` 完全一致，均带有 PEP 440 本地版本标记 `+mtnN`（形如 `4.29.4+mtn1`），由 `tests/maintained/test_version_marker.py` 强制校验。
- **纯基线版本号**：供严格调用 `packaging.version.Version()` 且不接受 local 段的场景使用 `astrbot.__version_base__`（即去掉 `+mtnN` 后的上游基线版本号，形如 `4.29.4`）。
- **基线锚点与发布标签**：上游基线使用附注标签 `baseline/*`（如 `baseline/v4.29.4`）长期保留；维护版发布标签格式为 `maintained/v<上游版本>-rN`（`N` 从 1 递增）。
- **分发范围**：本仓库遵循 AGPL-3.0-or-later 协议，仅打包并分发 core 本体（含构建后的 WebUI 静态资源），不包含任何第三方或私有插件。
