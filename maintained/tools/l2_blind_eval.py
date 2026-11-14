#!/usr/bin/env python3
"""L2 主动发言拟人化盲评抽样、四条红线机械检出与揭盲汇总脚本（纯标准库、只倒读日志尾部）。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

# T4 §2 四条一票否决红线正则（与量表严格一致）
ECHO_WHOLE_RE = re.compile(
    r"^(哈+|嘿+|草+|笑死|确实|是的+|对的+|没错|附议|赞同|有道理|牛+|6+|真的+|太真实了|我也觉得|嗯+|啊+|哦+|\?+|!+|！+|？+|。+|\.+)+$"
)
ECHO_TOKEN_RE = re.compile(
    r"(哈+|嘿+|草+|笑死|确实|是的+|对的+|没错|附议|赞同|有道理|牛+|6+|真的+|太真实了|我也觉得|嗯+|啊+|哦+)"
)
BRACKET_EMOJI_RE = re.compile(r"\[[^\[\]\n]{1,16}\]")
NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
HAS_DIGIT_OR_PROPER_RE = re.compile(r"(\d|[A-Za-z]{2,})")

SERVICE_POLITE_RE = re.compile(
    r"(您好|请问|很高兴为您|希望对[您你]有帮助|如有(其他|任何)问题|随时(告诉我|提问)|作为(一个|一款)?(AI|人工智能|机器人|语言模型|助手))"
)
SERVICE_STRUCT_RE = re.compile(
    r"(首先.*其次|第一[，、].*第二[，、]|综上所述|总而言之|从以下几个方面)",
    re.DOTALL,
)
SERVICE_LIST_RE = re.compile(r"^\s*([-*+]|\d+\.)\s", re.MULTILINE)

PARTICLE_END_RE = re.compile(r"(呢|呀|哦|啦|捏|喵|呐|哇)[~～！!。，,\s]*$")
PARTICLE_START_RE = re.compile(r"^(哈哈哈哈+|家人们|老铁们|宝子们|呜呜+)")
CLAUSE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")

COMPLAINT_KEYWORDS_RE = re.compile(r"(闭嘴|别吵|烦|乱回|刷屏|踢了|滚)")


def parse_local_ts(ts_str: str | None) -> dt.datetime | None:
    """解析 YYYY-MM-DD HH:MM:SS 或 ISO 格式本地时间戳。"""
    if not ts_str or not isinstance(ts_str, str):
        return None
    s = ts_str.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def read_jsonl_tail(
    path: Path,
    limit: int | None = None,
    since: str | None = None,
    block_size: int = 65536,
) -> list[dict[str, Any]]:
    """从文件尾部向前按块倒读 JSONL，避免几十 MB 日志全量进内存。

    由于 shadow_log.jsonl 按本地时间追加写入，当倒读遇到早于 --since 的记录时可提前终止。
    返回值按时间正序排列。
    """
    if not path.exists():
        return []

    since_dt = parse_local_ts(since) if since else None
    collected_reversed: list[dict[str, Any]] = []

    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        rem = b""
        stop_reading = False

        while pos > 0 and not stop_reading:
            read_len = min(block_size, pos)
            pos -= read_len
            f.seek(pos, os.SEEK_SET)
            chunk = f.read(read_len) + rem
            lines = chunk.split(b"\n")

            if pos > 0:
                rem = lines[0]
                lines_to_process = lines[1:]
            else:
                rem = b""
                lines_to_process = lines

            for raw_line in reversed(lines_to_process):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue

                row_dt = parse_local_ts(str(obj.get("ts") or ""))
                if since_dt is not None and row_dt is not None and row_dt < since_dt:
                    stop_reading = True
                    break

                collected_reversed.append(obj)
                if limit is not None and limit > 0 and len(collected_reversed) >= limit:
                    stop_reading = True
                    break

    collected_reversed.reverse()
    return collected_reversed


def is_empty_emotional_echo(text: str) -> bool:
    """T4 §2 红线 1：纯情绪附和判定。"""
    s = (text or "").strip()
    if not s:
        return True
    s_no_emoji = BRACKET_EMOJI_RE.sub("", s).strip()
    if ECHO_WHOLE_RE.match(s_no_emoji):
        return True
    if HAS_DIGIT_OR_PROPER_RE.search(s_no_emoji):
        return False
    stripped = ECHO_TOKEN_RE.sub("", s_no_emoji)
    stripped = NON_WORD_RE.sub("", stripped)
    return len(stripped) < 4


def is_service_tone_leak(text: str) -> bool:
    """T4 §2 红线 2：客服/顾问腔检出。"""
    s = (text or "").strip()
    if not s:
        return False
    if SERVICE_POLITE_RE.search(s):
        return True
    if SERVICE_STRUCT_RE.search(s):
        return True
    non_empty_paras = [p for p in s.splitlines() if p.strip()]
    if len(non_empty_paras) >= 3:
        return True
    if SERVICE_LIST_RE.search(s):
        return True
    if len(s) > 120:
        return True
    return False


def is_particle_spam(text: str) -> bool:
    """T4 §2 红线 3：语气词/情绪词污染检出。"""
    s = (text or "").strip()
    if not s:
        return False
    if s.count("~") + s.count("～") >= 2:
        return True
    if PARTICLE_START_RE.search(s):
        return True
    clauses = [c.strip() for c in CLAUSE_SPLIT_RE.split(s) if c.strip()]
    end_hits = sum(1 for c in clauses if PARTICLE_END_RE.search(c))
    if end_hits >= 2:
        return True
    return False


def check_live_complaint_or_recall(
    row: dict[str, Any],
    subsequent_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    """T4 §2 红线 4：真实发送后 180 秒内同群触发抱怨静默或人工撤回。"""
    flags: list[str] = []
    if not row.get("sent"):
        return flags

    if (
        row.get("recalled")
        or row.get("action") == "recall_done"
        or row.get("recall_done")
    ):
        flags.append("recalled")

    row_dt = parse_local_ts(str(row.get("ts") or ""))
    row_group = row.get("group")
    if row_dt is not None and row_group and subsequent_rows:
        for nxt in subsequent_rows:
            if nxt.get("group") != row_group:
                continue
            nxt_dt = parse_local_ts(str(nxt.get("ts") or ""))
            if nxt_dt is None:
                continue
            delta = (nxt_dt - row_dt).total_seconds()
            if delta < 0:
                continue
            if delta > 180:
                break
            skipped_by = str(nxt.get("skipped_by") or nxt.get("guard") or "")
            nxt_text = str(
                nxt.get("target") or nxt.get("reason") or nxt.get("text") or ""
            )
            if (
                skipped_by == "complaint_quiet"
                or nxt.get("complaint_triggered")
                or COMPLAINT_KEYWORDS_RE.search(nxt_text)
            ):
                flags.append("complaint_triggered")
                break
    return flags


def compute_mech_flags(
    text: str,
    row: dict[str, Any] | None = None,
    subsequent_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    """按 T4 §2 四条红线对单条候选文本与行记录打机械标签（纯函数）。"""
    flags: list[str] = []
    if text:
        if is_empty_emotional_echo(text):
            flags.append("empty_echo")
        if is_service_tone_leak(text):
            flags.append("service_tone")
        if is_particle_spam(text):
            flags.append("particle_spam")
    if row is not None:
        flags.extend(check_live_complaint_or_recall(row, subsequent_rows))
    return flags


BOT_NICKNAMES = tuple(
    name.strip()
    for name in os.environ.get("L2_BOT_NICKNAMES", "").split(",")
    if name.strip()
)


def normalize_candidate_text(
    text: str, bot_nicknames: tuple[str, ...] | None = None
) -> str:
    """T4 §3.3 表面混淆项清洗：剥离围栏、首尾空白、设备尾巴及机器人称呼。

    Nicknames are supplied through the environment so no deployment-specific
    name is checked in; without them only the generic prefixes are stripped.
    """
    s = (text or "").strip()
    s = re.sub(r"^```[\w-]*\s*|\s*```$", "", s).strip()
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"^(\[You[^\]]*\]|\[BOT\]|BOT[:：]\s*|机器人[:：]\s*)", "", s).strip()
    for nick in BOT_NICKNAMES if bot_nicknames is None else bot_nicknames:
        if nick:
            s = s.replace(nick, "群友")
    s = re.sub(r"\s+", " ", s)
    return s


def format_context_tail(row: dict[str, Any]) -> str:
    """将行内上下文格式化为脱敏的『[群友A] ...』多行展示字符串。"""
    ctx = row.get("context_tail") or row.get("context")
    if isinstance(ctx, list) and ctx:
        speaker_map: dict[str, str] = {}
        labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        rendered: list[str] = []
        for item in ctx[-5:]:
            if isinstance(item, dict):
                raw_u = str(
                    item.get("u") or item.get("role") or item.get("sender") or "U"
                )
                txt = str(item.get("t") or item.get("text") or "").strip()
            else:
                raw_u = "U"
                txt = str(item).strip()
            if not txt:
                continue
            if raw_u not in speaker_map:
                idx = min(len(speaker_map), len(labels) - 1)
                speaker_map[raw_u] = f"群友{labels[idx]}"
            rendered.append(f"[{speaker_map[raw_u]}] {txt}")
        if rendered:
            return "<br>".join(rendered)

    target = str(row.get("target") or "").strip()
    reason = str(row.get("reason") or "").strip()
    if target and reason:
        return f"[群友A] {target}<br>（背景：{reason}）"
    if target:
        return f"[群友A] {target}"
    if reason:
        return f"[话头背景] {reason}"
    return "[群友A] （见同群近期上下文切片）"


def extract_blind_samples(
    rows: list[dict[str, Any]],
    human_rows: list[dict[str, Any]] | None = None,
    n_persona: int = 30,
    n_human: int = 30,
    n_control: int = 15,
    seed: int = 20261115,
) -> list[dict[str, Any]]:
    """从 REPLY 行与可选真人语料中抽取『真人基准 / 走人格链 / 对照』三组盲样并打乱编码。"""
    rng = random.Random(seed)
    persona_pool: list[dict[str, Any]] = []
    control_pool: list[dict[str, Any]] = []
    human_pool: list[dict[str, Any]] = []

    for idx, r in enumerate(rows):
        sub_rows = rows[idx + 1 : idx + 30]
        if r.get("decision") == "REPLY":
            p_raw = str(r.get("persona_text") or "").strip()
            c_raw = str(r.get("persona_control") or r.get("control_text") or "").strip()
            ctx_str = format_context_tail(r)
            ht = r.get("hook_trace") if isinstance(r.get("hook_trace"), dict) else {}

            if p_raw:
                p_clean = normalize_candidate_text(p_raw)
                persona_pool.append(
                    {
                        "group_type": "persona",
                        "source_field": "persona_text",
                        "ts": str(r.get("ts") or ""),
                        "group": str(r.get("group") or "GROUP_A"),
                        "trace_id": str(r.get("trace_id") or ""),
                        "context": ctx_str,
                        "candidate": p_clean,
                        "mech_flags": compute_mech_flags(p_clean, r, sub_rows),
                        "hook_seen": ht.get("hook_seen"),
                        "sp_sha8": ht.get("sp_sha8") or "",
                        "persona_pos_pct": ht.get("persona_pos_pct"),
                    }
                )

            if c_raw:
                c_clean = normalize_candidate_text(c_raw)
                control_pool.append(
                    {
                        "group_type": "control",
                        "source_field": "persona_control",
                        "ts": str(r.get("ts") or ""),
                        "group": str(r.get("group") or "GROUP_A"),
                        "trace_id": str(r.get("trace_id") or ""),
                        "context": ctx_str,
                        "candidate": c_clean,
                        "mech_flags": compute_mech_flags(c_clean, r, None),
                        "hook_seen": False,
                        "sp_sha8": "",
                        "persona_pos_pct": None,
                    }
                )

        # 支持从行内 human_text / ground_truth 或非机器人的自然发言抽取真人基准（8~80 字配平）
        h_raw = str(r.get("human_text") or r.get("ground_truth") or "").strip()
        if not h_raw and r.get("kind") in ("user", "member", "human"):
            h_raw = str(r.get("text") or r.get("content") or "").strip()
        if h_raw:
            h_clean = normalize_candidate_text(h_raw)
            if 8 <= len(h_clean) <= 80 and not is_empty_emotional_echo(h_clean):
                human_pool.append(
                    {
                        "group_type": "human",
                        "source_field": "human_baseline",
                        "ts": str(r.get("ts") or ""),
                        "group": str(r.get("group") or "GROUP_A"),
                        "trace_id": str(r.get("trace_id") or ""),
                        "context": format_context_tail(r),
                        "candidate": h_clean,
                        "mech_flags": compute_mech_flags(h_clean, None, None),
                        "hook_seen": None,
                        "sp_sha8": "",
                        "persona_pos_pct": None,
                    }
                )

    if human_rows:
        for hr in human_rows:
            h_raw = str(
                hr.get("human_text") or hr.get("text") or hr.get("candidate") or ""
            ).strip()
            h_clean = normalize_candidate_text(h_raw)
            if 8 <= len(h_clean) <= 80 and not is_empty_emotional_echo(h_clean):
                human_pool.append(
                    {
                        "group_type": "human",
                        "source_field": "human_baseline",
                        "ts": str(hr.get("ts") or ""),
                        "group": str(hr.get("group") or "GROUP_A"),
                        "trace_id": str(hr.get("trace_id") or ""),
                        "context": format_context_tail(hr),
                        "candidate": h_clean,
                        "mech_flags": compute_mech_flags(h_clean, None, None),
                        "hook_seen": None,
                        "sp_sha8": "",
                        "persona_pos_pct": None,
                    }
                )

    # 若日志仅含 context_tail 中的真人句子而未单独带 human_text，从 context_tail 补充真人基准
    if len(human_pool) < n_human:
        seen_texts = {item["candidate"] for item in human_pool}
        for r in rows:
            ctx = r.get("context_tail")
            if isinstance(ctx, list) and len(ctx) >= 2:
                last_item = ctx[-1]
                txt = (
                    str(last_item.get("t") or last_item.get("text") or "").strip()
                    if isinstance(last_item, dict)
                    else str(last_item).strip()
                )
                clean_txt = normalize_candidate_text(txt)
                if (
                    8 <= len(clean_txt) <= 80
                    and clean_txt not in seen_texts
                    and not is_empty_emotional_echo(clean_txt)
                ):
                    seen_texts.add(clean_txt)
                    prev_Only = dict(r)
                    prev_Only["context_tail"] = ctx[:-1]
                    human_pool.append(
                        {
                            "group_type": "human",
                            "source_field": "context_tail_human",
                            "ts": str(r.get("ts") or ""),
                            "group": str(r.get("group") or "GROUP_A"),
                            "trace_id": str(r.get("trace_id") or ""),
                            "context": format_context_tail(prev_Only),
                            "candidate": clean_txt,
                            "mech_flags": compute_mech_flags(clean_txt, None, None),
                            "hook_seen": None,
                            "sp_sha8": "",
                            "persona_pos_pct": None,
                        }
                    )

    rng.shuffle(persona_pool)
    rng.shuffle(human_pool)
    rng.shuffle(control_pool)

    selected = (
        persona_pool[:n_persona] + human_pool[:n_human] + control_pool[:n_control]
    )
    rng.shuffle(selected)

    for i, item in enumerate(selected, start=1):
        digest = (
            hashlib.sha256(f"{seed}:{i}:{item['candidate']}".encode())
            .hexdigest()[:4]
            .upper()
        )
        item["blind_id"] = f"S-{i:03d}-{digest}"
        item["text_sha8"] = hashlib.sha256(
            item["candidate"].encode("utf-8")
        ).hexdigest()[:8]

    return selected


def write_blind_sheet_and_key(
    samples: list[dict[str, Any]],
    sheet_path: Path,
    key_path: Path,
    batch_id: str = "BLIND-L2-AUTO-01",
) -> None:
    """输出 blind_sheet.md（不含真值列）与单独的 blind_key.csv（揭盲映射）。"""
    ts_values = [s["ts"][:10] for s in samples if s.get("ts")]
    min_day = min(ts_values) if ts_values else "YYYY-MM-DD"
    max_day = max(ts_values) if ts_values else "YYYY-MM-DD"

    lines = [
        "# L2 拟人化盲评打分表",
        "",
        "## 1. 批次信息与评审员元数据",
        "",
        "| 项目 | 填写内容 |",
        "|---|---|",
        f"| **盲测批次编号** | `{batch_id}` |",
        "| **评审员代号** | `Reviewer-01` |",
        f"| **抽样群代号与时间窗** | `GROUP_A`（`{min_day}` ～ `{max_day}`） |",
        f"| **样本总数** | 共 `{len(samples)}` 条（真人基准 + 走人格链 + 对照，已打乱盲号） |",
        "| **评分规则速记** | **D1 信息与锐度**（0–3）｜**D2 群境承接**（0–3）｜**D3 去客服腔/句法自然**（0–3）｜**D4 分寸留白**（0–3）｜**P1 语气/情绪词惩罚**（0 / -1 / -2） |",
        "",
        "## 2. 逐条盲评打分表",
        "",
        "| 盲号 | 前序群聊上下文（最近 3～5 条，已脱敏） | 待评候选回复（盲样） | D1 信息(0-3) | D2 语境(0-3) | D3 去客服腔(0-3) | D4 分寸(0-3) | P1 语气词扣分(0/-1/-2) | 总分(-2~12) | 红线命中(附和/客服/伪前提) | 盲猜来源(真人 / Bot / 难辨) | 一句话判据 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for s in samples:
        ctx_cell = s["context"].replace("|", "｜").replace("\n", "<br>")
        cand_cell = s["candidate"].replace("|", "｜").replace("\n", " ")
        lines.append(
            f"| `{s['blind_id']}` | {ctx_cell} | {cand_cell} |  |  |  |  |  |  |  |  |  |"
        )

    sheet_content = "\n".join(lines) + "\n"
    sheet_path.write_text(sheet_content, encoding="utf-8")
    sheet_sha256 = hashlib.sha256(sheet_content.encode("utf-8")).hexdigest()

    with key_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "blind_id",
                "group_type",
                "source_field",
                "ts",
                "group",
                "trace_id",
                "mech_flags",
                "hook_seen",
                "sp_sha8",
                "persona_pos_pct",
                "text_sha8",
                "sheet_template_sha256",
            ],
        )
        writer.writeheader()
        for s in samples:
            writer.writerow(
                {
                    "blind_id": s["blind_id"],
                    "group_type": s["group_type"],
                    "source_field": s["source_field"],
                    "ts": s["ts"],
                    "group": s["group"],
                    "trace_id": s["trace_id"],
                    "mech_flags": ";".join(s["mech_flags"]),
                    "hook_seen": "" if s["hook_seen"] is None else str(s["hook_seen"]),
                    "sp_sha8": s["sp_sha8"],
                    "persona_pos_pct": ""
                    if s["persona_pos_pct"] is None
                    else str(s["persona_pos_pct"]),
                    "text_sha8": s["text_sha8"],
                    "sheet_template_sha256": sheet_sha256,
                }
            )


def parse_scored_sheet(sheet_path: Path) -> dict[str, dict[str, Any]]:
    """解析评审员填写后的 blind_sheet.md 表格行。"""
    scores: dict[str, dict[str, Any]] = {}
    for raw_line in sheet_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "`S-" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 11:
            continue
        blind_id = cells[0].strip("` ").strip()
        try:
            d1 = float(cells[3])
            d2 = float(cells[4])
            d3 = float(cells[5])
            d4 = float(cells[6])
            p1 = float(cells[7]) if cells[7] != "" else 0.0
        except ValueError:
            continue
        red_note = cells[9].strip()
        guess = cells[10].strip()
        scores[blind_id] = {
            "blind_id": blind_id,
            "candidate": cells[2],
            "D1": d1,
            "D2": d2,
            "D3": d3,
            "D4": d4,
            "P1": p1,
            "total": d1 + d2 + d3 + d4 + p1,
            "red_note": red_note,
            "guess": guess,
        }
    return scores


def evaluate_and_summarize(
    sheet_path: Path,
    key_path: Path,
    log_path: Path | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """合并 blind_sheet.md 评分与 blind_key.csv 揭盲真值，生成 T4 §5.3 汇总验收表与结论。"""
    scored = parse_scored_sheet(sheet_path)
    key_rows: dict[str, dict[str, str]] = {}
    with key_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key_rows[row["blind_id"]] = row

    grouped: dict[str, list[dict[str, Any]]] = {
        "human": [],
        "persona": [],
        "control": [],
    }
    for bid, kmeta in key_rows.items():
        if bid not in scored:
            continue
        gtype = kmeta["group_type"]
        if gtype not in grouped:
            continue
        s_item = dict(scored[bid])
        mflags = [x for x in (kmeta.get("mech_flags") or "").split(";") if x]
        # 若揭盲映射未预先计算完备，按候选文本补跑一次纯函数检出
        if not mflags and s_item.get("candidate"):
            mflags = compute_mech_flags(s_item["candidate"])
        s_item["mech_flags"] = mflags
        grouped[gtype].append(s_item)

    def summarize_group(items: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(items)
        if n == 0:
            return {
                "count": 0,
                "d1_mean": 0.0,
                "d2_mean": 0.0,
                "d3_mean": 0.0,
                "d4_mean": 0.0,
                "p1_rate": 0.0,
                "echo_rate": 0.0,
                "service_rate": 0.0,
                "particle_rate": 0.0,
                "human_like_rate": 0.0,
            }
        d1_mean = statistics.mean(x["D1"] for x in items)
        d2_mean = statistics.mean(x["D2"] for x in items)
        d3_mean = statistics.mean(x["D3"] for x in items)
        d4_mean = statistics.mean(x["D4"] for x in items)
        p1_hits = sum(
            1 for x in items if x["P1"] < 0 or "particle_spam" in x["mech_flags"]
        )
        echo_hits = sum(
            1
            for x in items
            if "empty_echo" in x["mech_flags"] or "附和" in x.get("red_note", "")
        )
        service_hits = sum(
            1
            for x in items
            if "service_tone" in x["mech_flags"] or "客服" in x.get("red_note", "")
        )
        particle_hits = sum(1 for x in items if "particle_spam" in x["mech_flags"])
        human_guesses = sum(
            1
            for x in items
            if any(tag in x["guess"] for tag in ("真人", "难辨", "Human", "Unsure"))
        )
        return {
            "count": n,
            "d1_mean": round(d1_mean, 2),
            "d2_mean": round(d2_mean, 2),
            "d3_mean": round(d3_mean, 2),
            "d4_mean": round(d4_mean, 2),
            "p1_rate": round(p1_hits / n, 4),
            "echo_rate": round(echo_hits / n, 4),
            "service_rate": round(service_hits / n, 4),
            "particle_rate": round(particle_hits / n, 4),
            "human_like_rate": round(human_guesses / n, 4),
        }

    stats_by_group = {k: summarize_group(v) for k, v in grouped.items()}

    # 若提供了原始 shadow_log.jsonl，同步核查真实发送投诉率与撤回率（红线 4）
    complaint_rate = 0.0
    recall_rate = 0.0
    sent_count = 0
    if log_path and log_path.exists():
        tail_rows = read_jsonl_tail(log_path, limit=limit, since=since)
        sent_indices = [i for i, r in enumerate(tail_rows) if r.get("sent")]
        sent_count = len(sent_indices)
        if sent_count > 0:
            c_hits = 0
            r_hits = 0
            for idx in sent_indices:
                r_flags = check_live_complaint_or_recall(
                    tail_rows[idx], tail_rows[idx + 1 : idx + 30]
                )
                if "complaint_triggered" in r_flags:
                    c_hits += 1
                if "recalled" in r_flags:
                    r_hits += 1
            complaint_rate = round(c_hits / sent_count, 4)
            recall_rate = round(r_hits / sent_count, 4)

    p_stat = stats_by_group["persona"]
    c_stat = stats_by_group["control"]

    reasons: list[str] = []
    if p_stat["count"] == 0:
        reasons.append("实验组（persona_text）样本数为 0")
    else:
        if p_stat["echo_rate"] > 0.0:
            reasons.append(
                f"触发红线 1：纯情绪附和占比 {p_stat['echo_rate'] * 100:.1f}% > 0%"
            )
        if p_stat["service_rate"] > 0.10:
            reasons.append(
                f"触发红线 2：客服/顾问腔检出率 {p_stat['service_rate'] * 100:.1f}% > 10%"
            )
        if p_stat["p1_rate"] > 0.05:
            reasons.append(
                f"触发红线 3：P1 语气词扣分/污染率 {p_stat['p1_rate'] * 100:.1f}% > 5%"
            )
        if complaint_rate > 0.01:
            reasons.append(
                f"触发红线 4：真实发送投诉率 {complaint_rate * 100:.1f}% > 1%"
            )
        if recall_rate > 0.02:
            reasons.append(f"触发红线 4：真实发送撤回率 {recall_rate * 100:.1f}% > 2%")
        if p_stat["d1_mean"] < 2.0:
            reasons.append(f"D1 信息均分 {p_stat['d1_mean']:.2f} < 2.0")
        if p_stat["d2_mean"] < 2.0:
            reasons.append(f"D2 语境均分 {p_stat['d2_mean']:.2f} < 2.0")
        if p_stat["d3_mean"] < 2.2:
            reasons.append(f"D3 去客服腔均分 {p_stat['d3_mean']:.2f} < 2.2")
        if p_stat["d4_mean"] < 2.2:
            reasons.append(f"D4 分寸均分 {p_stat['d4_mean']:.2f} < 2.2")
        if p_stat["human_like_rate"] < 0.40:
            reasons.append(
                f"被猜为『真人/难辨』比例 {p_stat['human_like_rate'] * 100:.1f}% < 40%"
            )
        if c_stat["count"] > 0:
            if c_stat["human_like_rate"] > 0.25:
                reasons.append(
                    f"对照组校准异常：对照组被猜为『真人/难辨』比例 {c_stat['human_like_rate'] * 100:.1f}% > 25%（评审员校准失效）"
                )
            if (p_stat["d3_mean"] - c_stat["d3_mean"]) < 1.0:
                reasons.append(
                    f"D3 较对照组提升不足：{p_stat['d3_mean'] - c_stat['d3_mean']:.2f} < 1.0"
                )

    passed = len(reasons) == 0
    h_stat = stats_by_group["human"]

    def fmt_row(label: str, st: dict[str, Any], status_cell: str) -> str:
        if st["count"] == 0:
            return (
                f"| **{label}** | 0 | — | — | — | — | — | — | — | — | {status_cell} |"
            )
        return (
            f"| **{label}** | {st['count']} | {st['d1_mean']:.2f} | {st['d2_mean']:.2f} | "
            f"{st['d3_mean']:.2f} | {st['d4_mean']:.2f} | {st['p1_rate'] * 100:.1f}% | "
            f"{st['echo_rate'] * 100:.1f}% | {st['service_rate'] * 100:.1f}% | "
            f"{st['human_like_rate'] * 100:.1f}% | {status_cell} |"
        )

    verdict_cell = "[x] 通过 / [ ] 驳回" if passed else "[ ] 通过 / [x] 驳回"
    ctrl_cell = (
        "校准有效"
        if (c_stat["count"] == 0 or c_stat["human_like_rate"] <= 0.25)
        else "校准失效（>25%）"
    )

    md_table = "\n".join(
        [
            "### 揭盲后汇总验收表（T4 §5.3）",
            "",
            "| 组别 | 样本数 | D1 均分 | D2 均分 | D3 去客服腔均分 | D4 均分 | P1 扣分触发率 | 纯附和红线率 | 客服腔检出率 | 被猜为「真人/难辨」比例（目标 ≥40%） | 是否通过验收 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
            fmt_row("真人基准组（Human）", h_stat, "基准参照"),
            fmt_row("实验组（`persona_text` 走钩子）", p_stat, verdict_cell),
            fmt_row("对照组（`persona_control` 不走钩子）", c_stat, ctrl_cell),
        ]
    )

    return {
        "passed": passed,
        "verdict": "PASS" if passed else "REJECT",
        "reasons": reasons,
        "sent_count": sent_count,
        "live_complaint_rate": complaint_rate,
        "live_recall_rate": recall_rate,
        "groups": stats_by_group,
        "markdown_table": md_table,
    }


def run_selftest() -> int:
    """内置自检：验证尾部倒读、--since/--limit、四条红线正则、盲表生成与揭盲判定全链路。"""
    # 1. 验证四条红线纯函数
    assert "empty_echo" in compute_mech_flags("哈哈哈确实！！")
    assert "empty_echo" not in compute_mech_flags(
        "5.0 那些所谓开门角色连官方爆料都还没有，别当成抽卡依据。"
    )
    assert "service_tone" in compute_mech_flags(
        "您好，首先建议您检查配置，其次重启服务，希望对您有帮助！"
    )
    assert "service_tone" in compute_mech_flags("- 第一步\n- 第二步")
    assert "particle_spam" in compute_mech_flags(
        "今天也是元气满满的一天呢~大家觉得呢呀~"
    )
    assert "particle_spam" in compute_mech_flags("家人们谁懂啊，这个角色太强啦！")

    base_row = {
        "ts": "2026-11-14 12:00:00",
        "group": "default:GroupMessage:10001",
        "sent": True,
    }
    next_rows = [
        {
            "ts": "2026-11-14 12:01:30",
            "group": "default:GroupMessage:10001",
            "skipped_by": "complaint_quiet",
        }
    ]
    assert "complaint_triggered" in compute_mech_flags("测试回复", base_row, next_rows)

    # 2. 构造临时 shadow_log.jsonl 并验证只倒读尾部 + 生成盲评表 + 揭盲打分验收
    with tempfile.TemporaryDirectory(prefix="l2_blind_selftest_") as tmpdir:
        tmp = Path(tmpdir)
        log_file = tmp / "shadow_log.jsonl"
        sheet_file = tmp / "blind_sheet.md"
        key_file = tmp / "blind_key.csv"

        sample_rows = []
        # 写入早于 --since 的旧记录，验证 --since 过滤
        sample_rows.append(
            {
                "ts": "2026-11-10 08:00:00",
                "group": "default:GroupMessage:10001",
                "mode": "live",
                "decision": "REPLY",
                "persona_text": "这条是旧记录，应当被 --since 过滤掉。",
                "persona_control": "您好，这是旧记录对照。",
                "sent": False,
            }
        )

        for i in range(10):
            sample_rows.append(
                {
                    "ts": f"2026-11-14 20:{i:02d}:00",
                    "group": "default:GroupMessage:10001",
                    "mode": "live",
                    "decision": "REPLY",
                    "reason": "纠正未官宣角色流言",
                    "target": "sp流萤会是5.0开门角色吗？",
                    "tone": "casual",
                    "context_tail": [
                        {"u": "U1", "t": "sp流萤会是5.0开门角色吗？"},
                        {
                            "u": "U2",
                            "t": f"别追通解，追你手上拉满的那队就行，内鬼图一半是P的（群友原话{i}）",
                        },
                    ],
                    "persona_text": f"5.0 那些开门角色连官方爆料都还没有，现在只算玩家猜测，别当抽卡依据（样本{i}）。",
                    "persona_control": f"您好！关于您提到的5.0版本角色问题，首先目前官方尚未公布，其次建议您理性看待（样本{i}）。",
                    "sent": True,
                    "trace_id": f"tr-20261114-{i:02d}",
                    "hook_trace": {
                        "hook_seen": True,
                        "sp_len_final": 1480,
                        "sp_sha8": "a91f4c2b",
                        "persona_marker": True,
                        "persona_pos_pct": 0.42,
                    },
                }
            )

        with log_file.open("w", encoding="utf-8") as f:
            for r in sample_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        tail = read_jsonl_tail(
            log_file, limit=15, since="2026-11-14 00:00:00", block_size=256
        )
        assert len(tail) == 10, f"Expected 10 rows after --since, got {len(tail)}"

        samples = extract_blind_samples(
            tail, n_persona=6, n_human=6, n_control=4, seed=42
        )
        assert len(samples) == 16
        write_blind_sheet_and_key(samples, sheet_file, key_file)
        assert sheet_file.exists() and key_file.exists()

        # 模拟评审员独立填分：根据 key 给三组填入符合预期分布的测试分值以验证汇总表计算
        key_map = {}
        with key_file.open("r", encoding="utf-8") as f:
            for kr in csv.DictReader(f):
                key_map[kr["blind_id"]] = kr["group_type"]

        filled_lines = []
        for line in sheet_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("| `S-"):
                parts = [c.strip() for c in line.strip("|").split("|")]
                bid = parts[0].strip("` ")
                gtype = key_map[bid]
                if gtype == "human":
                    row_scores = [
                        "3",
                        "3",
                        "3",
                        "3",
                        "0",
                        "12",
                        "无",
                        "真人",
                        "自然群友接话",
                    ]
                elif gtype == "persona":
                    row_scores = [
                        "3",
                        "2",
                        "2.5",
                        "2.5",
                        "0",
                        "10",
                        "无",
                        "真人",
                        "直接否定伪前提且无客套",
                    ]
                else:
                    row_scores = [
                        "2",
                        "2",
                        "0.5",
                        "1",
                        "0",
                        "5.5",
                        "客服",
                        "Bot",
                        "典型首先其次客服腔",
                    ]
                filled_lines.append(
                    f"| `{bid}` | {parts[1]} | {parts[2]} | "
                    + " | ".join(row_scores)
                    + " |"
                )
            else:
                filled_lines.append(line)
        sheet_file.write_text("\n".join(filled_lines) + "\n", encoding="utf-8")

        summary = evaluate_and_summarize(
            sheet_file,
            key_file,
            log_path=log_file,
            since="2026-11-14 00:00:00",
            limit=15,
        )
        assert summary["passed"] is True, (
            f"Selftest evaluation failed: {summary['reasons']}"
        )
        print(summary["markdown_table"])
        print(
            f"\n[SELFTEST OK] verdict={summary['verdict']}, samples={len(samples)}, tail_rows={len(tail)}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="L2 拟人化盲评抽样、红线机械检出与揭盲汇总脚本（标准库、离线只读）"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="运行内置离线自检并输出汇总表样例"
    )
    parser.add_argument(
        "--mode",
        choices=("flag", "prepare", "evaluate"),
        default="flag",
        help="执行模式：flag=尾部红线打标统计；prepare=生成盲评表与揭盲键；evaluate=读入评分生成汇总表",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("shadow_log.jsonl"),
        help="shadow_log.jsonl 路径",
    )
    parser.add_argument(
        "--human-log", type=Path, default=None, help="可选的真人基准语料 JSONL 路径"
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="起始本地时间过滤（如 '2026-11-14 00:00:00'）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="从文件尾部最多倒读的记录条数（默认 500）",
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        default=Path("blind_sheet.md"),
        help="盲评表 Markdown 路径",
    )
    parser.add_argument(
        "--key",
        type=Path,
        default=Path("blind_key.csv"),
        help="揭盲映射 CSV 路径（单独保存）",
    )
    parser.add_argument(
        "--n-persona", type=int, default=30, help="实验组（走人格链）抽样条数"
    )
    parser.add_argument("--n-human", type=int, default=30, help="真人基准组抽样条数")
    parser.add_argument("--n-control", type=int, default=15, help="阴性对照组抽样条数")
    parser.add_argument("--seed", type=int, default=20261115, help="随机打乱种子")
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()

    if args.mode == "flag":
        rows = read_jsonl_tail(args.log, limit=args.limit, since=args.since)
        flagged_summary = {
            "scanned_rows": len(rows),
            "reply_rows": 0,
            "flag_counts": {},
            "samples": [],
        }
        for idx, r in enumerate(rows):
            sub_rows = rows[idx + 1 : idx + 30]
            text = str(r.get("persona_text") or "").strip()
            flags = compute_mech_flags(text, r, sub_rows)
            r["mech_flags"] = flags
            if r.get("decision") == "REPLY":
                flagged_summary["reply_rows"] += 1
            for fl in flags:
                flagged_summary["flag_counts"][fl] = (
                    flagged_summary["flag_counts"].get(fl, 0) + 1
                )
            if flags and len(flagged_summary["samples"]) < 20:
                flagged_summary["samples"].append(
                    {
                        "ts": r.get("ts"),
                        "group": r.get("group"),
                        "decision": r.get("decision"),
                        "mech_flags": flags,
                        "hook_trace": r.get("hook_trace"),
                    }
                )
        print(json.dumps(flagged_summary, ensure_ascii=False, indent=2))
        return 0

    if args.mode == "prepare":
        rows = read_jsonl_tail(args.log, limit=args.limit, since=args.since)
        human_rows = (
            read_jsonl_tail(args.human_log, limit=args.limit, since=args.since)
            if args.human_log
            else None
        )
        samples = extract_blind_samples(
            rows,
            human_rows=human_rows,
            n_persona=args.n_persona,
            n_human=args.n_human,
            n_control=args.n_control,
            seed=args.seed,
        )
        write_blind_sheet_and_key(samples, args.sheet, args.key)
        print(
            json.dumps(
                {
                    "status": "prepared",
                    "total_blind_samples": len(samples),
                    "sheet_path": str(args.sheet),
                    "key_path": str(args.key),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.mode == "evaluate":
        res = evaluate_and_summarize(
            args.sheet, args.key, log_path=args.log, since=args.since, limit=args.limit
        )
        print(res["markdown_table"])
        print("\n## 验收判定结论\n")
        print(
            f"- **最终判定**：`{res['verdict']}`（{'通过' if res['passed'] else '驳回'}）"
        )
        if res["reasons"]:
            print("- **驳回原因**：")
            for reason in res["reasons"]:
                print(f"  - {reason}")
        else:
            print("- **全部四条红线与四维量表阈值均达标。**")
        return 0 if res["passed"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
