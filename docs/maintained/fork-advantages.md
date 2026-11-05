# 相比 AstrBot 基线，这个 fork 多了什么

> 2026-10-24。基线 = 上游 `v4.28.2`（`3c7adafa`）。
> 本文只列有证据的差异，并单列「有代价 / 还不成熟」的部分，客观陈述。

## 0. 一句话

上游解决的是「把大模型接进聊天平台」；这个 fork 额外解决的是
「升级之后还知道改了什么」和「插件做不到的事由谁来补」。

## 1. 上游痛点的直接对应

第三方评测对 AstrBot 的一致性批评有三条，这个 fork 恰好都有对应物：

| 上游痛点（评测原话） | 本 fork 的对应 |
|---|---|
| 插件质量参差、无 review | 改 core 必须过门禁：契约文档 + 测试常量 + 代码 `__all__` 三处同步，缺一处测试直接红（我这次加能力就被拦了 3 次） |
| 插件 API 无语义化版本 → 周更后插件静默失效 | 台账 + 漂移检测（见 §2） |
| 拟人化不如专注陪伴的项目 | `generate_with_persona`（见 §3） |

## 2. 台账与漂移检测（最独特的一项）

- `maintained/installed_manifest.json`：66 条受保护文件及其 SHA-256（56 core + 10 api）
- `maintained/tools/check_drift.py`：双端校验（仓库工作树 + 实例），退出码 0/1/2
- `maintained/tools/apply_patches.py`：一键重打（默认预演，`--apply` 才写）

上游没有这套东西。它的价值在 AstrBot 的更新节奏下被放大：
上游周更，插件/补丁随时可能被覆盖，覆盖是静默的。系统不会提示补丁缺失。
有了台账，`check_drift` 一行就能回答「我的改动还在不在」。

实测口径：仓库工作树 62/62 条哈希与磁盘字节一致（`mismatch: 0`）；实例侧双端校验需 `--instance`。

## 3. 底层能力：补「插件做不到」的部分

落点全部在 `astrbot/api/**`（遵循铁律 1），core 侧缺失时**优雅降级返回安全默认值**，
不抛出异常。补丁被覆盖后插件仍能正常导入。

| 公开模块 | 能力 |
|---|---|
| `api.turns` | 直发回合合并（文本/图片 URL） |
| `api.delivery` | 代码投递判定 |
| `api.permissions` | 执行授权判定 |
| `api.media` | 图片输入可用性契约 |
| `api.content` | 消息内容分块 |
| `api.runtime` | 运行时辅助 |
| `api.embedding` | 嵌入 provider |
| `api.proactive` | 主动场景标记 + 人格感知生成 |

其中 `api.proactive.generate_with_persona` 是我们这次新补的，也是最有代表性的一项：

`Context.llm_generate()` 和 `Context.tool_loop_agent()` 都直接调 provider，
跳过了 `on_llm_request` 钩子。人格、记忆与上下文插件依赖该钩子生效。
所以在基线上，插件无论怎么写都生成不了"带人格的话"。
本 fork 补的入口构造 `ProviderRequest` → 跑该钩子 → 再调 provider，
与 pipeline 内部 `internal.py:403` 同一做法。

实测对照（真实群消息，同一模型同一 prompt，唯一变量是走不走钩子）：

> 走钩子：低金通解本来就是伪命题…看策划给不给环境，别追通解，追你手上拉满的那队就行
> 不走钩：低金通解真没有，但这版本击破队盯着大丽花+阮梅走，生存位带加拉赫…

即：上游做不到的拟人化，这个 fork 让插件做得到了。

## 4. 安全加固（默认与上游一致，可选收紧）

| 项 | 内容 |
|---|---|
| `execution_gate_mode` | 默认 `legacy`（＝上游 admin-only）；可选 `strict`（执行意图判定）。默认不比上游严，也不比上游松 |
| 转述不授权 | strict 模式下「文档里写：先编译，再运行」不再被当成授权执行（基线会误判） |
| 拒答词表扩词 | 「我不能帮你写病毒/木马」这类真拒答不再被当成"代码没写完"而触发补生成 |
| 执行策略过滤器 | `apply_execution_policy` 尊重 gate 模式，legacy 下不删工具、不注入提示 |

要点：默认行为与上游一致（`legacy`），收紧是可选配置，以保持与上游兼容。
> ⚠️ 历史标注（2026-10-27）：以上是 T8 阶段为保上游测试的定调，不是当前总路线。当前路线为实用化分支：硬约束只是「上游插件不改也能跑」，允许改 core / WebUI，但要求每处改动可维护、动机可解释。


## 5. 工程纪律（可复用，不只是自用）

- 一改动一提交；改 core **必同步台账 SHA-256**
- 入仓文件强制 LF；哈希按**磁盘字节**算
- 测试门禁：`tests/maintained` **608 passed / 1 skipped**；上游全量 `pytest tests --ignore=tests/maintained` **2949 passed / 6 skipped / 2 xfailed**；含台账条数钉、api 契约、降级契约
- **本仓库只发布 core 本体，不包含任何插件**；插件不在打包与发布范围内

## 6. 诚实说明：有代价的 / 还不成熟的

1. **维护成本**：65 个受保护文件，上游每发一版都要重打 + 处理冲突。
   目前落后上游 **222 个提交**（v4.28.2 → v4.29.4；`git rev-list --count baseline/v4.28.2..v4.29.4`），追版本成本不低。
2. **上游 2 项测试有意偏离**（`config` 组：fork 给 `agent_runner.config.misc` 加了两个默认键，
   上游用精确字典相等断言）。已登记 P11 并加 `xfail(strict=True)` 守卫：若某次上游合并把偏离
   覆盖掉，测试会 `XPASS(strict)` 判红，即**偏离被静默回退时有机械报警**。
3. **`generate_with_persona` 的对照样本量偏小**：目前只有 8 条真实群消息的 A/B 对照
   （走钩子 vs 不走钩子），趋势可信但还不足以支撑定量结论。

## 7. 怎么验证本文的说法

```bash
# 台账哈希 vs 磁盘字节（无需实例）
python -c "import hashlib,json,pathlib; f=json.load(open('maintained/installed_manifest.json',encoding='utf-8'))['files']; print('mismatch:', sum(hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()!=v for k,v in f.items()))"
# 双端漂移检测（需要实例目录）
python maintained/tools/check_drift.py --instance "<实例目录>" --check-repo
# 测试（$TV = 装有项目依赖与 pytest 的 Python 3.12+ 解释器）
TMP=/d/pytest_tmp TEMP=/d/pytest_tmp "$TV" -m pytest tests/maintained -q
python maintained/proactive/replay.py --selftest     # 解析器 7 条，不调模型
```
