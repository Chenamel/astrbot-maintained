![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

<a href="./README.md">English</a> ｜ <a href="./README_zh.md">简体中文</a> ｜ <a href="./README_zh-TW.md">繁體中文</a> ｜ 日本語 ｜ <a href="./README_fr.md">Français</a> ｜ <a href="./README_es.md">Español</a> ｜ <a href="./README_ru.md">Русский</a>

<br>
<br>

[![version](https://img.shields.io/badge/version-4.28.2%2Bmtn1-blue)](https://github.com/Chenamel/astrbot-maintained/releases)
[![license](https://img.shields.io/badge/license-AGPL--3.0-green)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

</div>

これは AstrBot のメンテナンスブランチであり、ベースラインは上流の `v4.28.2` バージョンに固定されています。リポジトリは独立してメンテナンスされており、GitHub の fork ネットワークには含まれません。配布パッケージには core 本体のみが含まれ、プラグインは含まれません。ライセンスは AGPL-3.0-or-later であり、上流の作者とはいかなる提携関係もありません。

## コアの相違点と新規 API

上流の公式バージョンでは、一部の低レイヤーの状態が公開されていませんでした。この fork では `astrbot/api/**` 配下にインターフェースを追加し、これらの状態を公開しています。

`astrbot/api/` 配下には計 10 個の新規または変更されたファイルがあり、そのうち 8 個は機能モジュール、2 個は補助ファイルです。各機能モジュールは `available()` 関数を提供します。上流のオリジナル環境では、`available()` は `False` を返します。

| モジュール | 役割の説明 | 主なインターフェース |
|---|---|---|
| `api.turns` | ターン状態の判定、マージ後の原文と画像の取得 | `is_current` / `merged_text` / `merged_image_urls` / `mark_sent` |
| `api.proactive` | ペルソナと記憶チェーンを組み込んだ能動的返信の生成 | `generate_with_persona` / `persona_available` |
| `api.delivery` | 配信戦略の判定、テキストメッセージとファイル配信の区別 | `resolve` / `has_code_delivery` / `code_task_spec` |
| `api.permissions` | 実行権限の判定、管理者権限と今回の実行権限の区別 | `execution_denial` / `is_admin` |
| `api.media` | 視覚入力の可用性判定と画像キャプションの検出 | `has_visual_input` / `image_input_available` / `has_image_caption` |
| `api.content` | メッセージセグメントタイプの判定 | `is_text_part` / `is_image_part` |
| `api.runtime` | 実行パス、時間フォーマット、画像のダウンロードとタイミングモード | `get_astrbot_data_path` / `download_image_by_url` / `hook_timing_mode` |
| `api.embedding` | ベクトル化プロバイダーの判定 | `is_embedding_provider` |
| `api.event.extras` | イベント付加情報のキャリア | イベント追加プロトコルを参照 |
| `api._bridge` | 内部ブリッジ層（モジュール間の調整用、プラグインから直接呼び出すべきではありません） | — |

上流オリジナルの `Context.llm_generate` は下位モデルプロバイダーを直接呼び出すため、`on_llm_request` フックをバイパスし、ペルソナや記憶プラグインが無効化されていました。`generate_with_persona` はリクエストフックを先に実行し、これら 2 つのプラグインが通常どおり処理に参加できるようにします。

## 設定項目

4 つの設定項目が追加され、デフォルト値はすべて上流の公式動作と一致しています。

| 設定キー | デフォルト値 | 説明 |
|---|---|---|
| `execution_gate_mode` | `legacy` | 実行認可モード。デフォルトは上流と一致。`strict` に設定するとメッセージによる明示的な実行要求が必要 |
| `hook_timing_mode` | `legacy` | 完了フックのトリガータイミング。`enhanced` に設定すると返信送信前にフックがトリガーされる |
| `direct_turn_quiet_sec` | `4` | QQ メッセージ集約のサイレントウィンドウ（秒）。`0` に設定すると集約を無効化して即時処理 |
| `lightweight_proactive_tools` | リスト（計 29 項目） | 軽量能動ツールセットのホワイトリスト |

## 互換性

バージョン番号は `4.28.2+mtn1` です。`+mtn1` は PEP 440 の local セグメントであり、バージョン範囲の比較時には無視されます。

| 宣言方法 | 例 | 互換性判定 |
|---|---|---|
| 範囲宣言 | `>=4.16,<5` | 互換 |
| ベースライン一致 | `==4.28.2`、`~=4.28.0` | 互換 |
| 上位バージョン要求 | `>=4.29` | 拒否 |
| 厳密な等号一致 | `===4.28.2` | 拒否（PEP 440 の規則により文字列の完全一致が必要） |

ベースラインに対するテストでは、メンテナンス版と上流の両スイートが合格しました。既知の上流側の差異は別途登録されています。

## インストールと実行

環境要件は Python 3.12 以降です。

PyPI にはまだ公開されていないため、`pip install astrbot-maintained` ではインストールできません。

配布パッケージ名は `astrbot-maintained` ですが、Python のインポート名は同じく `astrbot` です。インポート名の競合を避けるため、インストール前に公式版をアンインストールしてください。

### wheel によるインストール

Releases ページから `.whl` ファイルをダウンロードします。ファイル名に `+` 文字が含まれているため、一部のシェルではクォートで囲むかエスケープする必要があります：

```bash
pip uninstall -y astrbot
pip install ./astrbot_maintained-4.28.2+mtn1-py3-none-any.whl
astrbot run
```

インストール後に起動し、ブラウザで `http://localhost:6185` にアクセスして管理パネルに入ります。

### ソースコードからの実行

本リポジトリをクローンした後、`uv` を使用して実行します：

```bash
uv sync && uv run main.py
```

### wheel のセルフビルド

WebUI パネルを含む wheel 生成物を自身でビルドする場合は、ビルド環境変数を指定する必要があります：

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

この環境変数が設定されていない場合、ビルド生成物に WebUI の静的ファイルは含まれません。

## アップデート確認と上流同期

パネルのアップデート確認は、デフォルトで本リポジトリの Releases を参照します：

- `update_source`: `https://api.github.com/repos/Chenamel/astrbot-maintained/releases`
- `update_repository`: `https://github.com/Chenamel/astrbot-maintained`

上流の `v4.29+` ではアーキテクチャが変更されており、ここに追加された低レイヤー API は存在しません。パネルから公式バージョンへ直接アップデートすると、変更されたコアファイルが上書きされ、インターフェースの欠落や動作異常の原因となります。

公式のアップデート追従に戻す必要がある場合は、管理パネルで `update_source` を `https://api.soulter.top/releases` に、`update_repository` を `https://github.com/AstrBotDevs/AstrBot` に変更してください。

## ドキュメント

- インストールの詳細、コンテナデプロイ、本 fork が動作していることの確認方法：[`docs/maintained/install.md`](./docs/maintained/install.md)
- プラグイン作成者のための 5 分間クイックスタート：[`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md)
- 各 API のパラメータ、戻り値、呼び出し例：[`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)
- API 設計制約とフォールバックメカニズム：[`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md)
- なぜこのようにレイヤー分けしたのか：[`docs/maintained/design.md`](./docs/maintained/design.md)
- 上流からの変更点：[`CHANGELOG.md`](./CHANGELOG.md)
- core 変更台帳（SHA-256、スクリプトによる検証が可能）：[`maintained/installed_manifest.json`](./maintained/installed_manifest.json)

## 過去の表現について

本 README の初期段階では、この層のインターフェースを「バックドア」（backdoor）と呼んでいましたが、現在は「インターフェース」（interface）に統一しています。

ミラーサイトや検索エンジンのキャッシュには古い表現が残っている可能性がありますが、現在の見解を示すものではありません。

これらのモジュールは公開され、ドキュメントが整備され、1 行ずつ確認できる Python API であり、認証を回避するような隠しエントリは一切含まれていません。

## ライセンス

本プロジェクトは上流と同様、AGPL-3.0-or-later ライセンスに基づいてオープンソースとして公開されています。詳細は LICENSE ファイルを参照してください。

本プロジェクトは独立してメンテナンスされているブランチであり、上流の作者とはいかなる提携関係もありません。
