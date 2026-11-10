# 升级覆盖审计（`sync_audit.py`）

> 解决的是「撞到一个修一个」：追上游大版本后，台账 68 条、门禁 8 项、
> 645 条测试都可能全绿，但实例仍会因为没有同步上游新增模块而启动失败，
> 或因为上游改了函数签名而让 fork 包装层静默失效。
> 本方法以**两个上游基线之间的全量变更面**为参照，检查 fork 是否覆盖，
> 而不是只检查 fork 自己改过的文件。

## 方法定义

参照物固定为两个已推送的 annotated tag：

- `baseline/v4.28.2` — 升级前的上游基线
- `baseline/v4.29.4` — 升级后的上游基线

审计对象 = 当前工作树 + 可选的运行实例。所有检查**只读**，不写文件、不执行修复。
输出按 `BLOCK / WARN / INFO / SKIP` 分级，每条带 `id`、文件与行号、证据、修复建议；
`--json` 输出同结构，供 CI 与脚本消费。退出码：有 `BLOCK` 为 1，否则 0。

| ID | 层 | 检查 | 对应已发生的事故 |
|---|---|---|---|
| S1 | 静态 | 上游改动过签名的函数，其调用点是否仍传已删除的 kwarg / 超量位置参数 | `prepare_model_image()` 删参后主动回复图片准备静默失效 |
| S2 | 静态 | 两个基线间上游新增的 `astrbot/**/*.py` 是否都在当前树 | 合并后文件齐全，但实例没同步到 |
| S3 | 静态 | 上游新增依赖是否进 `requirements.txt` 且与 `pyproject.toml` 一致 | 实例 venv 缺 `opentelemetry-sdk`，启动崩在日志系统之前 |
| S4 | 静态 | `dashboard/src` 的本地 import 是否都能解析到真实文件 | 上游删了 `SidebarCustomizer.vue`，`pnpm build` 失败 |
| S5 | 静态 | 四语言 `features/*.json` 是否都在该语言 `index.ts` import 且挂载 | 上游改动态 loader，fork 的 `calls.json` 漏迁导致整页 `[MISSING]` |
| S6 | 静态 | `dashboard/dist/assets/version` 是否等于 `v{__version__}`，且 fork 词条在产物中 | 旧面板导致更新误报与配置页语言丢失 |
| S7 | 静态 | `astrbot/**` 的 Python import 是否都解析到真实模块 | 上游删模块后实例崩在日志系统之前，`check_drift` 仍全绿 |
| S8 | 静态 | 两个基线的 `astrbot/api/all.py` 导出是否一个都没少 | 插件兼容硬约束：少一个导出，上游插件就 ImportError |
| I1 | 实例 | `astrbot/**` **全量**逐文件与仓库比对（不是只比台账 68 条） | 缺 26 个上游新增模块、143 个旧文件，启动失败 |
| I2 | 实例 | S3 的新增依赖在实例 venv 中能否 import | 同上 |
| I3 | 实例 | `data/dist_maintained` 是否与 `dashboard/dist` 逐文件一致 | 面板没随升级重编 |
| I4 | 实例 | `maintained_build.json` 的 commit 是否等于当前 HEAD | 门禁 build stamp 红 |
| I5 | 实例 | 上游新增配置键是否在 `cmd_config.json`（`WARN`，可能是可选配置） | `trace_*` 新键 |

`SKIP` 表示前提不满足（如 CI 上没有构建产物、没传 `--instance`），不算通过也不算失败，
报告里必须显式列出，避免「没检查」被误读成「检查通过」。

**已内建的误报豁免**（都是实测踩过的）：

- S4 只判本地路径（`@/`、`./`），npm 包名交给打包器；`*DEPRECATED*` 死文件里的悬空 import 降为 `INFO`。
- S1 里「上游删掉的符号」若 fork 有意保留该模块且当前树仍有定义，不报 —— fork 保留旧实现是正当的。
- S7 跳过 `try` 保护的可选导入，只认 `astrbot` / `astrbot.*`，不把 `astrbot_config` 这类顶层兼容模块当子模块。
- I1 排除 `astrbot/dashboard/dist`（本地构建产物；实例面板由 I3 单独校验）。
- I5 用 AST 只取 `DEFAULT_CONFIG` 的**顶层**键，不把嵌套 schema 子键当配置项。

## 用法

```bash
# 静态层：CI / 本地都能跑，不需要实例
PYTHONPATH=maintained python -m tools.sync_audit

# 完整：加运行实例
PYTHONPATH=maintained python -m tools.sync_audit \
  --instance "C:/Users/philia093/.astrbot_launcher/instances/<uuid>"

# 机器读
PYTHONPATH=maintained python -m tools.sync_audit --json
```

结果不确定时不猜：S1 无法解析的调用降级为 `INFO` 并注明原因；`SKIP` 必须写明缺哪个前提。

## 接入点

- **CI 已接入**：`maintained-ci.yml` 的 `static-checks` job 跑静态层；checkout 必须
  `fetch-depth: 0` + `fetch-tags: true`，否则两个基线取不到，审计会退化成 `SKIP`。
- **已绑定的补充 job**：同一 workflow 的 `dashboard-build`（`pnpm run i18n:check` + `vue-tsc` +
  `vite build`）与 `upstream-suite`（上游全套 `tests/`）在每次 push / PR / 手动触发时都跑。上游的
  `dashboard_ci.yml` 带 `github.repository == 'AstrBotDevs/AstrBot'` 守卫（fork 上整段跳过），
  `unit_tests.yml` 等 6 个又在仓库设置里 `disabled_manually`，所以这两个 job 是 fork 专属替代。
  它们先以 `workflow_dispatch`-only 观察过一次全绿（run `42832585578`），再解除触发限制；
  全套上游测试约 5 分钟，`timeout-minutes` 留了 45。
- **自测**：`tests/maintained/test_sync_audit.py` 用构造样例验证 S1/S4/S5/S7/S8/I1
  确实能报出已知四类事故，并守住上面的误报豁免。
- 本地发布：`release_gate.py` 已覆盖 lint / manifest / dashboard / README 环 / 两套测试 / drift / stamp，
  本工具**不重复**这些；先跑本工具（`--instance`），再跑门禁 8 项，两者都过才算可发。
- 运行时错误（重启后新 ERRO / 新 WARN 文本）由 `instance_check.py` 与晨检覆盖，本工具不重复实现。

## 已覆盖与不覆盖

覆盖：上游**结构/契约/依赖/资源**变化没被 fork 或实例吸收的静态可判定项。

不覆盖：上游行为语义变化（同样签名但含义变了）、第三方中转服务与平台侧扣费归因、
模型输出质量、并发时序竞争。这些仍需真实运行与人工复核。

每次追版本后：先跑本工具 → 修完所有 `BLOCK` → 再跑门禁 8 项 → 才考虑合并发布。
