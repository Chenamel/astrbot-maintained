"""Read-only memory sampler for a running instance (roadmap stage A).

The question being answered is whether the Python process is *leaking* (usage
climbing steadily) or simply carrying a *high-water mark* from a large
one-off allocation. Those two look identical in a single snapshot, so this
appends a row per run and reports the slope between samples.

Nothing here writes to the instance except the CSV of its own samples.

Usage::

    python maintained/tools/mem_sample.py --instance "<instance dir>"            # take a sample
    python maintained/tools/mem_sample.py --instance "<instance dir>" --report    # show the trend
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path

#: Dashboard port; the AstrBot process owns it.
PANEL_PORT = "6185"
SHADOW_LOG = "core/data/plugins/astrbot_plugin_proactive_shadow/shadow_log.jsonl"

FIELDS = [
    "unix_ts",
    "local_time",
    "working_set_mb",
    "private_mb",
    "virtual_mb",
    "threads",
    "handles",
    "judgements_total",
    "judgements_last_hour",
]


def _run(args: list[str]) -> str:
    """Run a command and return its stdout, tolerating Windows encodings."""
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return proc.stdout or ""


def find_pid() -> int | None:
    """Find the AstrBot process id via the dashboard port it listens on."""
    out = _run(["netstat", "-ano"])
    for line in out.splitlines():
        if f":{PANEL_PORT}" in line and "LISTENING" in line:
            pid = line.split()[-1]
            if pid.isdigit():
                return int(pid)
    return None


def read_memory(pid: int) -> dict:
    """Read process counters through WMIC (no psutil dependency)."""
    out = _run(
        [
            "wmic",
            "process",
            "where",
            f"processid={pid}",
            "get",
            "WorkingSetSize,PrivatePageCount,VirtualSize,ThreadCount,HandleCount",
            "/format:csv",
        ]
    )
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if len(lines) < 2:
        return {}
    # Resolve columns by name: relying on WMIC's ordering silently swapped
    # private bytes with the thread count.
    header = lines[0].split(",")
    values = lines[1].split(",")
    cols = dict(zip(header, values))
    try:
        return {
            "working_set_mb": round(int(cols["WorkingSetSize"]) / 1024 / 1024),
            "private_mb": round(int(cols["PrivatePageCount"]) / 1024 / 1024),
            "virtual_mb": round(int(cols["VirtualSize"]) / 1024 / 1024),
            "threads": int(cols["ThreadCount"]),
            "handles": int(cols["HandleCount"]),
        }
    except (KeyError, ValueError):
        return {}


def read_judgements(instance: Path) -> tuple[int, int]:
    """Total decisions recorded, and how many in the last hour."""
    path = instance / SHADOW_LOG
    if not path.exists():
        return 0, 0
    total = 0
    recent = 0
    cutoff = time.time() - 3600
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("source") == "replay":
                continue
            total += 1
            stamp = rec.get("ts", "")
            try:
                if time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S")) >= cutoff:
                    recent += 1
            except (ValueError, OverflowError):
                continue
    return total, recent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="只读的实例内存采样")
    ap.add_argument("--instance", required=True, help="实例目录")
    ap.add_argument("--report", action="store_true", help="只打印趋势，不采样")
    args = ap.parse_args(argv)
    instance = Path(args.instance)
    csv_path = instance / "core/data/mem_samples.csv"

    if args.report:
        return _report(csv_path)

    pid = find_pid()
    if pid is None:
        print("找不到 AstrBot 进程（面板端口未监听）")
        return 2
    mem = read_memory(pid)
    if not mem:
        print(f"读不到进程 {pid} 的内存计数")
        return 2
    total, recent = read_judgements(instance)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if fresh:
            writer.writeheader()
        writer.writerow(
            {
                "unix_ts": int(time.time()),
                "local_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                **mem,
                "judgements_total": total,
                "judgements_last_hour": recent,
            }
        )

    print(f"PID {pid}  {time.strftime('%H:%M:%S')}")
    print(
        f"  工作集 {mem['working_set_mb']} MB | 私有 {mem['private_mb']} MB | 虚拟 {mem['virtual_mb']} MB"
    )
    print(f"  线程 {mem['threads']} | 句柄 {mem['handles']}")
    print(f"  判定 累计 {total} | 最近 1 小时 {recent}")
    print(f"  已记录 → {csv_path}")
    _print_delta(csv_path)
    return 0


def _print_delta(csv_path: Path) -> None:
    rows = _rows(csv_path)
    if len(rows) < 2:
        print("  （首个采样点，暂无趋势；过一段时间再采一次）")
        return
    first, last = rows[0], rows[-1]
    hours = (int(last["unix_ts"]) - int(first["unix_ts"])) / 3600
    if hours <= 0:
        return
    ws = int(last["working_set_mb"]) - int(first["working_set_mb"])
    priv = int(last["private_mb"]) - int(first["private_mb"])
    print(
        f"  趋势（{hours:.1f}h，{len(rows)} 个采样点）："
        f"工作集 {ws:+d} MB、私有 {priv:+d} MB"
    )


def _rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8") as handle:
        return [r for r in csv.DictReader(handle) if r.get("unix_ts")]


def _report(csv_path: Path) -> int:
    rows = _rows(csv_path)
    if not rows:
        print("还没有采样数据")
        return 1
    print(f"{'时间':<20}{'工作集MB':>10}{'私有MB':>9}{'线程':>6}{'判定累计':>10}")
    for row in rows:
        print(
            f"{row['local_time']:<20}{row['working_set_mb']:>10}"
            f"{row['private_mb']:>9}{row['threads']:>6}{row['judgements_total']:>10}"
        )
    _print_delta(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
