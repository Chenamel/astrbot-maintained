![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

<a href="./README.md">English</a> ｜ <a href="./README_zh.md">简体中文</a> ｜ 繁體中文 ｜ <a href="./README_ja.md">日本語</a> ｜ <a href="./README_fr.md">Français</a> ｜ <a href="./README_es.md">Español</a> ｜ <a href="./README_ru.md">Русский</a>

<br>
<br>

[![version](https://img.shields.io/badge/version-4.28.2%2Bmtn1-blue)](https://github.com/Chenamel/astrbot-maintained/releases)
[![license](https://img.shields.io/badge/license-AGPL--3.0-green)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

</div>

這是 AstrBot 的維護分支，基準鎖定在上游 `v4.28.2` 版本。倉庫獨立維護，不在 GitHub 的 fork 網絡裡。分發包只包含 core 本體，不含插件。許可證是 AGPL-3.0-or-later，與上游作者無從屬關係。

## 核心差異與新增 API

上游官方版本沒有公開部分底層狀態。這個 fork 在 `astrbot/api/**` 下補了接口，把這些狀態開放出來。

`astrbot/api/` 下共有 10 個新增或變動文件，其中 8 個是功能模組，2 個是輔助文件。每個功能模組都提供 `available()` 函數。在上游原版環境中，`available()` 返回 `False`。

| 模組 | 職責說明 | 主要接口 |
|---|---|---|
| `api.turns` | 回合狀態判定，獲取合併後的原文與圖片 | `is_current` / `merged_text` / `merged_image_urls` / `mark_sent` |
| `api.proactive` | 接入人格與記憶鏈的主動回復生成 | `generate_with_persona` / `persona_available` |
| `api.delivery` | 交付策略判定，區分文本消息與文件交付 | `resolve` / `has_code_delivery` / `code_task_spec` |
| `api.permissions` | 執行授權判定，區分管理員身份與本次執行授權 | `execution_denial` / `is_admin` |
| `api.media` | 視覺輸入可用性判定與圖片說明檢測 | `has_visual_input` / `image_input_available` / `has_image_caption` |
| `api.content` | 消息段類型判定 | `is_text_part` / `is_image_part` |
| `api.runtime` | 運行路徑、時間格式化、圖片下載與時序模式 | `get_astrbot_data_path` / `download_image_by_url` / `hook_timing_mode` |
| `api.embedding` | 向量化提供方判定 | `is_embedding_provider` |
| `api.event.extras` | 事件附加信息載體 | 見事件附加協議 |
| `api._bridge` | 內部橋接層，供模組間協調，插件不應直接調用 | — |

上游原版的 `Context.llm_generate` 直接調用底層模型提供方，跳過了 `on_llm_request` 鉤子，人格與記憶插件因此失效。`generate_with_persona` 會先執行請求鉤子，讓這兩個插件照常參與進來。

## 配置項

新增了 4 個配置項，默認值都與上游官方行為一致。

| 配置鍵 | 默認值 | 說明 |
|---|---|---|
| `execution_gate_mode` | `legacy` | 執行授權模式。默認與上游一致；設為 `strict` 要求消息顯式請求執行 |
| `hook_timing_mode` | `legacy` | 完成鉤子觸發時序。設為 `enhanced` 時鉤子在回復發出前觸發 |
| `direct_turn_quiet_sec` | `4` | QQ 消息聚合靜默窗口秒數。設為 `0` 則關閉聚合立即處理 |
| `lightweight_proactive_tools` | 列表（共 29 項） | 輕量主動工具集白名單列表 |

## 兼容性

版本號是 `4.28.2+mtn1`。其中 `+mtn1` 是 PEP 440 的 local 段，在版本區間比較時會被忽略。

| 聲明方式 | 示例 | 兼容判定 |
|---|---|---|
| 區間聲明 | `>=4.16,<5` | 兼容 |
| 基準匹配 | `==4.28.2`、`~=4.28.0` | 兼容 |
| 高版本要求 | `>=4.29` | 拒絕 |
| 嚴格等號匹配 | `===4.28.2` | 拒絕（PEP 440 規則要求字符串全量相等） |

針對基準的測試中，維護版與上游兩套測試均通過；少數已知的上游偏差另行登記。

## 安裝與運行

環境要求 Python 3.12 或更高版本。

尚未發布到 PyPI，`pip install astrbot-maintained` 裝不上。

分發包名為 `astrbot-maintained`，Python 導入名同為 `astrbot`。安裝前先卸官方版，避免導入名衝突。

### 使用 wheel 安裝

從 Releases 頁面下載 `.whl` 文件。文件名帶 `+` 字符，在部分 shell 中需要引號包裹或轉義：

```bash
pip uninstall -y astrbot
pip install ./astrbot_maintained-4.28.2+mtn1-py3-none-any.whl
astrbot run
```

安裝後啟動，瀏覽器訪問 `http://localhost:6185` 進入管理面板。

### 源碼運行

克隆本倉庫後使用 `uv` 運行：

```bash
uv sync && uv run main.py
```

### 自行構建 wheel

自行構建包含 WebUI 面板的 wheel 產物時，需要指定構建環境變量：

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

未設置該環境變量時，構建產物不會包含 WebUI 靜態文件。

## 更新檢查與上游同步

面板的更新檢查默認指向本倉庫 Releases：

- `update_source`: `https://api.github.com/repos/Chenamel/astrbot-maintained/releases`
- `update_repository`: `https://github.com/Chenamel/astrbot-maintained`

上游 `v4.29+` 架構已變更，沒有這裡新增的底層 API。若從面板直接更新到官方版本，修改過的核心文件會被覆蓋，導致接口缺失與運行異常。

若需要恢復跟隨官方更新，在管理面板中將 `update_source` 修改為 `https://api.soulter.top/releases`，將 `update_repository` 修改為 `https://github.com/AstrBotDevs/AstrBot`。

## 文檔

- 安裝細節、容器部署、如何確認跑的是本 fork：[`docs/maintained/install.md`](./docs/maintained/install.md)
- 插件作者 5 分鐘入門：[`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md)
- 每個 API 的參數、返回值、調用示例：[`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)
- API 設計約束與降級機制：[`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md)
- 為什麼這樣分層：[`docs/maintained/design.md`](./docs/maintained/design.md)
- 相對上游改了什麼：[`CHANGELOG.md`](./CHANGELOG.md)
- core 改動台賬（SHA-256，可腳本校驗）：[`maintained/installed_manifest.json`](./maintained/installed_manifest.json)

## 關於歷史表述

本 README 早期把這層接口叫過「後門」，現在統一叫「接口」。

鏡像站和搜索緩存裡可能還是舊說法，那不代表現在的立場。

這些模組是公開、有文檔、能逐行看的 Python API，不包含任何繞過鑑權的隱蔽入口。

## 許可證

本項目依據 AGPL-3.0-or-later 協議開源，與上游一致。詳見 LICENSE 文件。

本項目為獨立維護分支，與上游作者無從屬關係。
