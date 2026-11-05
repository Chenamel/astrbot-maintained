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

在 `astrbot/core/config/default.py` 的配置 schema 里新增了 fork 独有的键时。

## 步骤

1. 补语言包（4 种语言各一份，纯新增）：

   `dashboard/src/i18n/locales/{zh-CN,en-US,ja-JP,ru-RU}/features/config-metadata.json`

   路径与 schema 键对应，例如：
   - `ai_group.agent_computer_use.provider_settings.<key>` → `{ "description": …, "hint": … }`
   - `ai_group.others.agent_runner.config.misc.<key>` → 同上

   ⚠️ 用按行插入保住原文件排版；`json.dumps` 整文件重写会产生上千行噪音 diff
   （ru-RU 实测 2055 行）。插入时注意：末尾键没有尾逗号，新词条要插在它前面。

2. 构建（在 `dashboard/` 下）：

   ```bash
   CI=true pnpm install --registry=https://registry.npmmirror.com
   CI=true pnpm build
   ```

   坑：
   - 项目锁文件是 **lockfileVersion 9.0**，只能用 **pnpm 10**（pnpm 12 不读
     `package.json` 的 `pnpm.overrides`，会报 `ERR_PNPM_VERIFY_DEPS_BEFORE_RUN`）
   - 非交互环境必须 `CI=true`，否则 `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`
   - 构建会顺带重新生成 `src/assets/mdi-subset/*`，那是工具链噪音，**不要提交**

3. **版本标记**（已自动化，通常无需手动处理）：

   `pnpm build` 末尾已接 `npm run stamp`，会调用
   `scripts/stamp_dashboard_version.py` 把 `astrbot.__version__`（当前 `4.28.2+mtn1`）
   加 `v` 前缀后写入 `dashboard/dist/assets/version`（当前 `v4.28.2+mtn1`）。

   单独补写或校验时：

   ```bash
   python ../scripts/stamp_dashboard_version.py           # 写入当前包版本
   python ../scripts/stamp_dashboard_version.py --check   # 缺失或过期则退出码 1
   ```

   ⚠️ **不要手写该文件**。戳记内容是 `v` + `astrbot.__version__`（含 `+mtnN` 后缀），
   `resolve_dashboard_dist()` 按此逐字符比较；写成 `v4.28.2` 会被判为不匹配，
   进而触发重新下载官方面板，覆盖本 fork 的构建。

4. **部署到实例**：

   ```bash
   mv <instance>/core/data/dist <instance>/core/data/dist.bak-<时间戳>
   cp -r dashboard/dist <instance>/core/data/dist
   ```

   面板静态资源是每次请求读盘的，**刷新浏览器即可生效，无需重启机器人**。
   验证：`grep -rl "<新词条>" <instance>/core/data/dist/assets/*.js`

## 红线边界

改动仅限：语言包 JSON（纯新增词条）+ 构建产物（实例侧 `data/dist`，不入仓）。
**不碰** dashboard 的业务代码与页面结构，避免与上游合并冲突。
