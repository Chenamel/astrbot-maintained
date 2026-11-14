# Dashboard（WebUI）构建与部署

> 本分支新增的配置项必须在 dashboard 语言包中登记，否则配置页会直接显示原始键路径（如 `ai_group.agent_computer_use.provider_settings.execution_gate_mode.description`）。配置页按路径查找 `features/config-metadata.json`，未命中时回退显示键名。

## 打包发布时必须带上 dist

构建 wheel 时，钩子仅在设置 `ASTRBOT_BUILD_DASHBOARD=1` 时才会编译并打包前端面板：

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

未设置该变量生成的 wheel 不包含面板静态资源，安装后访问 6185 端口将没有界面。可用以下命令校验 wheel 内面板文件数量（完整构建应输出约 272）：

```bash
python -c "import zipfile,glob;z=zipfile.ZipFile(glob.glob('*.whl')[0]);print(sum('dashboard/dist/' in n for n in z.namelist()))"
```

`astrbot/dashboard/dist/` 已列入 `.gitignore`，构建产物不直接提交进源码树。

## 何时需要重新构建并部署面板

- 在 `astrbot/core/config/default.py` 的配置 schema 中新增了本分支独有的配置键时。
- **每次合并上游新版本后，必须重新编译并部署 `dist_maintained`。** 若沿用旧构建，面板会缺少上游新增的 `config-metadata` 词条而显示 `[MISSING: ...]`，且 `assets/version` 戳记落后于当前 core 版本（`maintained/VERSION`）时会触发 `versionsMismatch(core, dashboard)`，导致页面顶部误报「WebUI 有新版本」并引导下载官方面板覆盖本地构建。面板静态资源按请求实时读盘，重新部署后强刷浏览器即可生效，无需重启机器人。

## 构建步骤

1. 补充四份语言包（纯新增词条）：

   `dashboard/src/i18n/locales/{zh-CN,en-US,ja-JP,ru-RU}/features/config-metadata.json`

   路径与 schema 键一一对应，例如：
   - `ai_group.agent_computer_use.provider_settings.<key>` → `{ "description": "...", "hint": "..." }`
   - `ai_group.others.agent_runner.config.misc.<key>` → 同上

   ⚠️ 请按行插入新词条以保留原文件缩进与排版，避免用 `json.dumps` 重写整份文件产生大面积格式 diff；注意 JSON 末尾键无尾逗号，新词条应插在末尾键之前。

   ⚠️ 语言包由 `locales/<lang>/index.ts` 逐语言组装。新增 `features/*.json` 后必须在四份 `index.ts` 中同步补充 import 与挂载，否则构建虽能通过，运行时会显示 `[MISSING: ...]`。`tests/maintained/test_i18n_registry.py` 会对此做静态校验。

   ⚠️ 修改任何语言包后请运行 `CI=true pnpm run i18n:check`，校验四份语言包的叶子键集合与 `zh-CN` 基线双向完全一致；`sync_audit.py` 的 S5 仅检查文件是否挂载，不检查文件内部键集合漂移。

2. 编译前端（在 `dashboard/` 目录下）：

   ```bash
   CI=true pnpm install --registry=https://registry.npmmirror.com
   CI=true pnpm build
   ```

   注意事项：
   - 锁文件为 **lockfileVersion 9.0**，必须使用 **pnpm 10**（pnpm 12 不会读取 `package.json` 中的 `pnpm.overrides`，会报错 `ERR_PNPM_VERIFY_DEPS_BEFORE_RUN`）。
   - 非交互环境下必须加上 `CI=true`，否则会报 `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`。
   - 构建过程会重新生成 `src/assets/mdi-subset/*`：日常仅改文案时无需提交；跨上游版本升级导致图标集变化时，应将更新后的图标子集一并提交，保持源码与构建产物一致。

3. **写入版本戳记**（已集成至 `pnpm build` 末尾的 `npm run stamp`）：

   构建脚本会自动调用 `scripts/stamp_dashboard_version.py`，将 `'v' + astrbot.__version__`（与 `maintained/VERSION` 一致，形如 `v4.29.4+mtn1`）写入 `dashboard/dist/assets/version`。

   单独补写或校验命令：

   ```bash
   python ../scripts/stamp_dashboard_version.py           # 写入当前包版本
   python ../scripts/stamp_dashboard_version.py --check   # 缺失或不一致时返回退出码 1
   ```

   ⚠️ 请勿手动编辑该文件。`resolve_dashboard_dist()` 会将该文件内容与 `'v' + astrbot.__version__`（含 `+mtnN` 后缀）逐字符比对；若写成不含本地段的上游版本号（形如 `v4.29.4`），会被判定为版本不匹配并触发官方面板下载。

4. **部署到普通实例**（不使用 AstrBot Launcher 时）：

   ```bash
   mv <实例目录>/core/data/dist <实例目录>/core/data/dist.bak-<时间戳>
   cp -r dashboard/dist <实例目录>/core/data/dist
   ```

   刷新浏览器即可生效，并用以下命令确认新词条已打入构建产物：
   `grep -rl "<新词条>" <实例目录>/core/data/dist/assets/*.js`

   ⚠️ 使用 AstrBot Launcher 管理的实例请勿直接覆盖 `data/dist`，否则会被启动器自动回滚，请按下一节部署。

## 使用 AstrBot Launcher 时：面板必须放独立目录

启动器每次启动实例时都会执行部署预检（`launch_instance()` → `deploy_instance()`），其中 `ensure_webui_for_version()` 会读取 `<实例目录>/core/data/dist/assets/version` 并与启动器登记的上游版本号（形如 `v4.29.4`）做字符串比对（不做 PEP 440 本地段归一化）。若 `data/dist/assets/version` 带有 `+mtnN` 后缀，启动器会判定版本不符并从上游下载官方 `dashboard.zip` 覆盖 `data/dist`。

因此需保留 `data/dist` 为启动器预期的官方版本，同时将维护版面板放入独立目录 `data/dist_maintained`，通过环境变量 `ASTRBOT_WEBUI_DIR` 引导 core 加载。

### 部署步骤

1. 保持 `<实例目录>/core/data/dist` 为启动器生成的官方版本不变，使启动器预检直接跳过下载。
2. 将维护版面板复制到独立目录：

   ```bash
   mkdir -p <实例目录>/core/data/dist_maintained
   cp -r dashboard/dist/. <实例目录>/core/data/dist_maintained/
   ```

3. 设置用户级环境变量 `ASTRBOT_WEBUI_DIR` 指向该目录（设置后需重启启动器进程使其继承新环境变量）：

   Windows（PowerShell，用户级）：

   ```powershell
   [Environment]::SetEnvironmentVariable(
       'ASTRBOT_WEBUI_DIR',
       '<实例目录>\core\data\dist_maintained',
       'User'
   )
   ```

   撤销命令：`[Environment]::SetEnvironmentVariable('ASTRBOT_WEBUI_DIR', $null, 'User')`。

4. 重启启动器并启动实例，确认日志中出现 `Using WebUI directory: ...dist_maintained`，强刷浏览器检查配置页词条显示正常。

目录解析优先级：`--webui-dir` 命令行参数 > `ASTRBOT_WEBUI_DIR` 环境变量 > 默认 `data/dist`。

### 注意事项与版本接口口径

- `ASTRBOT_WEBUI_DIR` 为用户级环境变量，同机其他从 `main.py` 启动的实例也会读取该变量；若某实例下不存在该路径，`check_dashboard_files()` 会打印 `WebUI directory not found ... Using default.` 并安全回退到默认目录。
- `dist_maintained/assets/version` 必须保持为带 `+mtnN` 后缀的维护版版本号（形如 `v4.29.4+mtn1`），供 `resolve_dashboard_dist()` 校验。
- `/api/updates/check` 与 `/api/stats/version` 会从 `app.state.dashboard_static_folder` 读取当前实际提供服务的面板目录及其 `assets/version` 戳记，未指定自定义目录时回退到 `data/dist`。因此通过 `ASTRBOT_WEBUI_DIR` 挂载 `dist_maintained` 时，面板版本会正确显示为当前维护版版本号（形如 `v4.29.4+mtn1`），不会因读取到 `data/dist` 下的官方版本戳记而误报更新。

## 修改边界

面板侧改动仅限 `dashboard/src/i18n/locales/` 语言包 JSON 新增词条与构建产物部署，不修改 dashboard 页面组件与前端业务逻辑，避免上游合并冲突。
