![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

English ｜ <a href="./README_zh.md">简体中文</a> ｜ <a href="./README_zh-TW.md">繁體中文</a> ｜ <a href="./README_ja.md">日本語</a> ｜ <a href="./README_fr.md">Français</a> ｜ <a href="./README_es.md">Español</a> ｜ <a href="./README_ru.md">Русский</a>

<br>
<br>

[![version](https://img.shields.io/badge/version-4.28.2%2Bmtn1-blue)](https://github.com/Chenamel/astrbot-maintained/releases)
[![license](https://img.shields.io/badge/license-AGPL--3.0-green)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

</div>

This is a maintained branch of AstrBot, with its baseline locked to upstream version `v4.28.2`. The repository is maintained independently and is detached from GitHub's fork network. Distribution packages contain only core itself, with no plugins included. The license is AGPL-3.0-or-later, with no affiliation with the upstream authors.

## Core Differences and New APIs

The upstream official release does not expose certain underlying states. This fork adds interfaces under `astrbot/api/**` to expose these states.

There are 10 new or modified files under `astrbot/api/`, consisting of 8 functional modules and 2 helper files. Each functional module provides an `available()` function. In the original upstream environment, `available()` returns `False`.

| Module | Description | Primary Interfaces |
|---|---|---|
| `api.turns` | Turn status evaluation, retrieving merged raw text and images | `is_current` / `merged_text` / `merged_image_urls` / `mark_sent` |
| `api.proactive` | Proactive reply generation integrated with persona and memory chain | `generate_with_persona` / `persona_available` |
| `api.delivery` | Delivery strategy evaluation, distinguishing text messages from file delivery | `resolve` / `has_code_delivery` / `code_task_spec` |
| `api.permissions` | Execution authorization evaluation, distinguishing admin status from per-execution authorization | `execution_denial` / `is_admin` |
| `api.media` | Visual input availability evaluation and image caption detection | `has_visual_input` / `image_input_available` / `has_image_caption` |
| `api.content` | Message segment type evaluation | `is_text_part` / `is_image_part` |
| `api.runtime` | Runtime paths, time formatting, image downloading, and timing mode | `get_astrbot_data_path` / `download_image_by_url` / `hook_timing_mode` |
| `api.embedding` | Vectorization provider evaluation | `is_embedding_provider` |
| `api.event.extras` | Carrier for event additional information | See event additional protocol |
| `api._bridge` | Internal bridge layer for inter-module coordination; plugins should not call directly | — |

The original upstream `Context.llm_generate` directly calls the underlying model provider, bypassing the `on_llm_request` hook and causing persona and memory plugins to fail. `generate_with_persona` executes the request hook first, allowing both plugins to participate as expected.

## Configuration Options

Added 4 new configuration options, all defaulting to match upstream official behavior.

| Config Key | Default | Description |
|---|---|---|
| `execution_gate_mode` | `legacy` | Execution authorization mode. Defaults to match upstream; set to `strict` to require messages to explicitly request execution |
| `hook_timing_mode` | `legacy` | Completion hook trigger timing. Set to `enhanced` to trigger the hook before the reply is sent |
| `direct_turn_quiet_sec` | `4` | QQ message aggregation quiet window in seconds. Set to `0` to disable aggregation and process immediately |
| `lightweight_proactive_tools` | List (29 items in total) | Whitelist for lightweight proactive tools |

## Compatibility

The version number is `4.28.2+mtn1`. The `+mtn1` suffix is the local segment under PEP 440, which is ignored during version range comparisons.

| Declaration Style | Example | Compatibility Result |
|---|---|---|
| Range declaration | `>=4.16,<5` | Compatible |
| Baseline matching | `==4.28.2`, `~=4.28.0` | Compatible |
| Higher version requirement | `>=4.29` | Rejected |
| Strict equal matching | `===4.28.2` | Rejected (PEP 440 rules require exact string equality) |

In tests against the baseline, both the maintained suite and the upstream suite pass; the few known upstream deviations are registered separately.

## Installation and Running

Requires Python 3.12 or higher.

Not yet published to PyPI; `pip install astrbot-maintained` will not work.

The distribution package name is `astrbot-maintained`, while the Python import name remains `astrbot`. Uninstall the official version before installing to prevent import name conflicts.

### Installing via wheel

Download the `.whl` file from the Releases page. The filename contains a `+` character, which requires quotes or escaping in some shells:

```bash
pip uninstall -y astrbot
pip install ./astrbot_maintained-4.28.2+mtn1-py3-none-any.whl
astrbot run
```

Start after installation, then visit `http://localhost:6185` in your browser to access the admin dashboard.

### Running from Source

Clone this repository and run with `uv`:

```bash
uv sync && uv run main.py
```

### Building the wheel Yourself

When building a wheel distribution containing the WebUI dashboard yourself, specify the build environment variable:

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

If this environment variable is not set, the build output will not include WebUI static files.

## Update Checks and Upstream Syncing

Dashboard update checks point to this repository's Releases by default:

- `update_source`: `https://api.github.com/repos/Chenamel/astrbot-maintained/releases`
- `update_repository`: `https://github.com/Chenamel/astrbot-maintained`

The upstream `v4.29+` architecture has changed and does not include the underlying APIs added here. Updating directly to the official version from the dashboard will overwrite modified core files, leading to missing interfaces and runtime errors.

To resume following official updates, change `update_source` to `https://api.soulter.top/releases` and `update_repository` to `https://github.com/AstrBotDevs/AstrBot` in the admin dashboard.

## Documentation

- Installation details, container deployment, and verifying you are running this fork: [`docs/maintained/install.md`](./docs/maintained/install.md)
- 5-minute quickstart for plugin authors: [`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md)
- Parameters, return values, and call examples for each API: [`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)
- API design constraints and fallback mechanisms: [`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md)
- Why layered this way: [`docs/maintained/design.md`](./docs/maintained/design.md)
- What changed relative to upstream: [`CHANGELOG.md`](./CHANGELOG.md)
- Core modification ledger (SHA-256, script-verifiable): [`maintained/installed_manifest.json`](./maintained/installed_manifest.json)

## Regarding Historical Phrasing

An early version of this README referred to this layer of interfaces as "backdoors"; they are now consistently referred to as "interfaces".

Mirror sites and search engine caches may still display the old phrasing, which does not reflect the current position.

These modules are public, documented, and fully auditable Python APIs line by line, containing no hidden entry points that bypass authentication.

## License

This project is open-sourced under the AGPL-3.0-or-later license, consistent with upstream. See the LICENSE file for details.

This project is an independently maintained branch and has no affiliation with the upstream authors.
