# 升级覆盖审计（`sync_audit.py`）

> `check_drift.py` 仅校验本分支修改过的台账文件；追上游版本时，若上游新增了模块、依赖或修改了未进台账的函数签名，仅靠台账检查无法发现。
> `sync_audit.py` 以两个上游基线标签之间的全量变更面为参照，静态核对代码树与运行实例是否完整吸收了上游变更。

## 方法定义

审计参照物为两次上游同步各自推送的附注标签（升级前基线与升级后基线），可通过 `git tag -l 'baseline/*'` 查看当前基线标签。

审计对象为当前工作树及可选的运行实例。所有检查均为只读操作，不修改任何文件。
输出结果按 `BLOCK / WARN / INFO / SKIP` 分级，包含检查项 `id`、文件路径与行号、证据摘要及修复建议；支持 `--json` 输出供 CI 与脚本消费。存在任何 `BLOCK` 项时退出码为 `1`，否则为 `0`。

| ID | 层级 | 检查内容 | 典型故障场景 |
|---|---|---|---|
| S1 | 静态 | 上游修改过签名的函数，其调用点是否仍传入已删除的 kwarg 或超量位置参数 | `prepare_model_image()` 删参后主动回复图片准备静默失效 |
| S2 | 静态 | 两个基线之间上游新增的 `astrbot/**/*.py` 是否均存在于当前工作树 | 合并后仓库有文件，但运行实例未同步新增模块 |
| S3 | 静态 | 上游新增依赖是否已写入 `requirements.txt` 且与 `pyproject.toml` 一致 | 实例虚拟环境缺少新增依赖（如 `opentelemetry-sdk`）导致启动崩溃 |
| S4 | 静态 | `dashboard/src` 下的本地相对导入是否均能解析到真实文件 | 上游删除旧组件（如 `SidebarCustomizer.vue`）导致 `pnpm build` 失败 |
| S5 | 静态 | 四份语言包的 `features/*.json` 是否均在对应 `index.ts` 中导入并挂载 | 上游重构语言加载器时漏挂新增词条文件导致页面显示 `[MISSING]` |
| S6 | 静态 | `dashboard/dist/assets/version` 是否等于 `v{__version__}` 且包含本分支新增词条 | 沿用旧版面板构建产物导致更新误报与配置项词条缺失 |
| S7 | 静态 | `astrbot/**` 内的 Python 导入是否均能解析到真实模块 | 上游删除内部模块后实例在日志初始化前崩溃，而台账哈希检查仍通过 |
| S8 | 静态 | 两个基线之间 `astrbot/api/all.py` 的导出符号是否零删减 | 少导出任何一个公开符号即破坏上游插件兼容性 |
| I1 | 实例 | 实例 `astrbot/**` 全量文件与仓库工作树逐一比对 | 实例缺失上游新增模块或残留过期文件导致启动失败 |
| I2 | 实例 | S3 识别出的新增依赖在实例虚拟环境中是否可导入 | 实例未同步安装新增依赖 |
| I3 | 实例 | 实例 `data/dist_maintained` 是否与仓库 `dashboard/dist` 逐文件一致 | 面板未随核心升级重新编译部署 |
| I4 | 实例 | 实例 `maintained_build.json` 记录的 commit 是否等于当前仓库 `HEAD` | 实例运行代码与当前仓库提交脱节 |
| I5 | 实例 | 上游新增顶层配置键是否已存在于实例 `cmd_config.json`（记为 `WARN`） | 提醒检查上游新增可选配置项 |

`SKIP` 表示当前运行环境不满足检查前提（例如未生成前端构建产物或未传 `--instance`），在报告中显式列出，不与「检查通过」混淆。

**内置误报豁免规则**：

- S4 仅检查本地路径导入（`@/`、`./`），第三方 npm 包交由打包器验证；`*DEPRECATED*` 文件中的悬空导入降级为 `INFO`。
- S1 中若上游删除了某符号，但本分支有意保留该模块且当前工作树中仍有定义，则不报错。
- S7 跳过 `try...except` 保护的可选导入，仅检查 `astrbot` 与 `astrbot.*` 命名空间，忽略 `astrbot_config` 等顶层兼容模块。
- I1 自动排除 `astrbot/dashboard/dist`（实例面板由 I3 独立校验）。
- I5 仅通过 AST 提取 `DEFAULT_CONFIG` 的顶层键，忽略嵌套 schema 子键。

## 用法

```bash
# 静态层检查（CI 与本地均可直接运行，无需实例）
PYTHONPATH=maintained python -m tools.sync_audit

# 完整检查（静态层 + 运行实例层）
PYTHONPATH=maintained python -m tools.sync_audit \
  --instance "<实例目录>"

# 结构化 JSON 输出
PYTHONPATH=maintained python -m tools.sync_audit --json
```

对于 S1 中无法静态确定的动态调用，工具会降级为 `INFO` 并附上原因，不做猜测。

## CI 与发布流程接入

- **CI 静态门禁**：`maintained-ci.yml` 的 `static-checks` 任务默认运行静态层审计；checkout 需配置 `fetch-depth: 0` 与 `fetch-tags: true` 以确保能读取 `baseline/*` 标签。
- **配套校验任务**：同一 workflow 中的 `dashboard-build`（执行 `pnpm run i18n:check`、`vue-tsc`、`vite build`）与 `upstream-suite`（执行上游全量 `tests/`）在每次推送与 PR 时自动运行。全套上游测试耗时约 5 分钟，`timeout-minutes` 设为 45 分钟。
- **回归自测**：`tests/maintained/test_sync_audit.py` 使用构造样本验证 S1/S4/S5/S7/S8/I1 的故障检出能力与豁免规则。
- **本地发布顺序**：先运行 `sync_audit.py --instance "<实例目录>"` 清零全部 `BLOCK` 项，再运行 `release_gate.py` 执行 8 项发布门禁。
- **运行时监控分工**：实例重启后的运行时错误日志由 `instance_check.py` 与 `daily_check.py` 覆盖。

## 覆盖边界

- **已覆盖**：上游模块结构、函数签名、依赖包、前端资源与导出列表变更是否被仓库工作树及运行实例完整吸收。
- **不覆盖**：函数签名不变但内部行为语义改变、第三方中转服务状态、模型生成质量与并发时序竞争。
