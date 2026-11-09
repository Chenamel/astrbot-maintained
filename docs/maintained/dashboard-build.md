# Dashboard（WebUI）构建与部署

> 本分支新增的配置项必须在 dashboard 语言包里登记，否则配置页会显示原始键路径
> （例如 `ai_group.agent_computer_use.provider_settings.execution_gate_mode.description`）。
> 原因：配置页按路径查 `features/config-metadata.json`，查不到就回退显示键名。

## 打包发布时：必须带上 dist

打 wheel 时钩子只在 `ASTRBOT_BUILD_DASHBOARD=1` 下才构建并复制面板：

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

不带该变量会得到一个没有面板的 wheel：装上去 `astrbot run` 后 6185 端口没有界面。
校验（应输出约 272）：

```bash
python -c "import zipfile,glob;z=zipfile.ZipFile(glob.glob('*.whl')[0]);print(sum('dashboard/dist/' in n for n in z.namelist()))"
```

`astrbot/dashboard/dist/` 已列入 `.gitignore`，构建产物不入库。

## 什么时候需要走这套流程

- 在 `astrbot/core/config/default.py` 的配置 schema 里新增了 fork 独有的键时。
- **每次追上游大版本后必须重编并重新部署 `dist_maintained`。** 旧构建的语言包缺新版
  config-metadata 词条，配置页会显示 `[MISSING: ...]` 或原始键路径；`assets/version`
  仍是旧版本时，`versionsMismatch(core, dashboard)` 成立，顶部会误报「WebUI 有新版本」
  并引导下载官方面板覆盖 fork 构建。重编后静态资源每次请求读盘，**强刷浏览器即可，
  无需重启机器人**。

## 步骤

1. 补语言包（4 种语言各一份，纯新增）：

   `dashboard/src/i18n/locales/{zh-CN,en-US,ja-JP,ru-RU}/features/config-metadata.json`

   路径与 schema 键对应，例如：
   - `ai_group.agent_computer_use.provider_settings.<key>` → `{ "description": …, "hint": … }`
   - `ai_group.others.agent_runner.config.misc.<key>` → 同上

   ⚠️ 用按行插入保住原文件排版；`json.dumps` 整文件重写会产生上千行噪音 diff
   （ru-RU 实测 2055 行）。插入时注意：末尾键没有尾逗号，新词条要插在它前面。

   ⚠️ 4.29.4 起语言包由 `locales/<lang>/index.ts` 逐语言组装。新增 `features/*.json`
   后必须在**四份** index.ts 都补 import 与挂载，否则构建照样成功、运行时却显示
   `[MISSING: ...]`。`tests/maintained/test_i18n_registry.py` 会守这一点。

2. 构建（在 `dashboard/` 下）：

   ```bash
   CI=true pnpm install --registry=https://registry.npmmirror.com
   CI=true pnpm build
   ```

   坑：
   - 项目锁文件是 **lockfileVersion 9.0**，只能用 **pnpm 10**（pnpm 12 不读
     `package.json` 的 `pnpm.overrides`，会报 `ERR_PNPM_VERIFY_DEPS_BEFORE_RUN`）
   - 非交互环境必须 `CI=true`，否则 `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`
   - 构建会顺带重新生成 `src/assets/mdi-subset/*`：日常构建属工具链噪音，不要提交；
     **跨大版本时图标集确实变了（上游会删旧图标、加新图标），应连同新 css 一起提交**，
     否则仓库源码与发布产物长期不一致、每次构建都出现 diff

3. **版本标记**（已自动化，通常无需手动处理）：

   `pnpm build` 末尾已接 `npm run stamp`，会调用
   `scripts/stamp_dashboard_version.py` 把 `astrbot.__version__`（当前 `4.29.4+mtn1`）
   加 `v` 前缀后写入 `dashboard/dist/assets/version`（当前 `v4.29.4+mtn1`）。

   单独补写或校验时：

   ```bash
   python ../scripts/stamp_dashboard_version.py           # 写入当前包版本
   python ../scripts/stamp_dashboard_version.py --check   # 缺失或过期则退出码 1
   ```

   ⚠️ **不要手写该文件**。戳记内容是 `v` + `astrbot.__version__`（含 `+mtnN` 后缀），
   `resolve_dashboard_dist()` 按此逐字符比较；写成 `v4.29.4` 会被判为不匹配，
   进而触发重新下载官方面板，覆盖本 fork 的构建。

4. **部署到实例**（不使用 AstrBot Launcher 时）：

   ```bash
   mv <instance>/core/data/dist <instance>/core/data/dist.bak-<时间戳>
   cp -r dashboard/dist <instance>/core/data/dist
   ```

   面板静态资源是每次请求读盘的，**刷新浏览器即可生效，无需重启机器人**。
   验证：`grep -rl "<新词条>" <instance>/core/data/dist/assets/*.js`

   ⚠️ 使用 AstrBot Launcher 时**不要这样做**，会被启动器回滚，见下一节。

## 使用 AstrBot Launcher 时：面板必须放独立目录

启动器每次启动都会跑一次部署预检（`launch_instance()` → `deploy_instance()`），
其中 `ensure_webui_for_version()` 读取

```text
<instance>/core/data/dist/assets/version
```

并与实例清单里登记的版本比较。启动器登记的是上游版本号 `v4.29.4`，比较时
只忽略大小写和 `v` 前缀，**不做 PEP 440 归一化**。因此本 fork 的戳记
`v4.29.4+mtn1` 会被判为不匹配，启动器随后从上游下载 `dashboard.zip`
并整体替换 `data/dist`。表现是启动时在 WebUI 阶段卡一会儿，日志里看不到
下载记录（下载由启动器进程完成）。

core 自己不是覆盖者：`ensure_dashboard()` 的版本比较会忽略 local 段，
判定 `v4.29.4` 与 `4.29.4+mtn1` 兼容后直接返回。

启动器没有自定义仓库或版本源的开关，仓库地址与面板下载地址都写在源码里；
高级设置页只有代理和镜像源。能用的是 core 这一侧的目录选择。

### 部署步骤

1. `data/dist` **保持启动器给的官方版本**（`v4.29.4`），不要动。版本匹配时
   启动器会直接跳过下载，启动也不会卡。

2. 把本 fork 的面板放到启动器不管理的独立目录：

   ```bash
   mkdir -p <instance>/core/data/dist_maintained
   cp -r dashboard/dist/. <instance>/core/data/dist_maintained/
   ```

3. 设 `ASTRBOT_WEBUI_DIR` 指向该目录。启动器启动的 python 子进程会继承
   用户级环境变量，但**已运行的启动器不会重新读环境变量，需要重启启动器**。

   Windows（PowerShell，用户级）：

   ```powershell
   [Environment]::SetEnvironmentVariable(
       'ASTRBOT_WEBUI_DIR',
       '<instance>\core\data\dist_maintained',
       'User'
   )
   ```

   撤销：`[Environment]::SetEnvironmentVariable('ASTRBOT_WEBUI_DIR', $null, 'User')`。

4. 重启启动器并启动实例，日志里应出现 `Using WebUI directory: ...dist_maintained`。
   浏览器强刷一次，确认配置页能显示新增配置项的说明文字而不是键路径。

优先级：`--webui-dir` 命令行参数 > `ASTRBOT_WEBUI_DIR` > 默认目录。
启动器不提供自定义启动参数，所以实际生效的是环境变量这一层。

### 两点注意

- 这个环境变量是**进程级的全局值**，同机其他 AstrBot 实例也会读到。
  单机多实例时，要么都指向同一份 fork 面板，要么改用 `--webui-dir`
  自行启动（启动器不支持传参）。
- 从仓库重新同步面板后，`dist_maintained` 里的 `assets/version` 仍是
  `v4.29.4+mtn1`，**不要改成 `v4.29.4`**。core 的 `resolve_dashboard_dist()`
  会拿它和包版本比较。

### 环境变量的作用域

`ASTRBOT_WEBUI_DIR` 设成**用户级环境变量**后，同一台机器上的其他 AstrBot 实例
也会继承它。只有本 fork 的 `main.py` 入口会读（wheel 的 `astrbot run` 走 CLI，
不受影响）；若某个实例没有它指向的目录，`check_dashboard_files()` 会打印
`WebUI directory not found ... Using default.` 并回退到默认面板，不会启动失败。
新增实例时检查这个变量是否仍指向正确目录，不用时按上面的命令撤销。

### 版本接口读的是实际服务的目录

`/api/updates/check` 与 `/api/stats/version` 都要报告面板版本。早期实现调用
`get_dashboard_version()` 不带参数，它只会读 `data/dist/assets/version`，
不知道 `--webui-dir` / `ASTRBOT_WEBUI_DIR` 指定的目录。在上面的部署下就会
出现「WebUI 有新版本！」并把当前版本显示成 `v4.29.4`：接口拿官方占位目录的
戳记去和 core 的 `v4.29.4+mtn1` 做字符串比较，并不代表真有更新可装。

现在两个接口都从 `app.state.dashboard_static_folder` 取实际服务的目录再读戳记；
读不到时退回原来的优先级。因此启动器部署下显示 `v4.29.4+mtn1`，不再误报。
普通 wheel / 源码安装没有显式目录，行为与之前一致。

## 红线边界

改动仅限：语言包 JSON（纯新增词条）+ 构建产物（实例侧 `data/dist`，不入仓）。
**不碰** dashboard 的业务代码与页面结构，避免与上游合并冲突。
