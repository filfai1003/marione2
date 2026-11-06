"""A line in the log every few minutes about the bot's memory, to find what makes it grow.

Railway bills the container's memory (what the kernel counts for it, page cache included), so the
line says where it sits: the Python process itself (`rss`), anonymous memory and file cache of the
whole container (`anon`, `file`), threads, child processes (ffmpeg, deno, stockfish) and the
Python lines whose allocations grew the most since the previous line. Linux only: elsewhere the
parts that cannot be read are left out.
"""

import asyncio
import logging
import os
import tracemalloc
from pathlib import Path

logger = logging.getLogger("marione.memory")

INTERVAL = 600.0
CGROUP = Path("/sys/fs/cgroup")


def _mb(kib: int) -> str:
    return f"{kib / 1024:.0f}MB"


def _status(pid: str) -> dict[str, str]:
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return {}
    return dict(line.split(":", 1) for line in text.splitlines() if ":" in line)


def _kib(status: dict[str, str], key: str) -> int:
    try:
        return int(status.get(key, "0 kB").split()[0])
    except (ValueError, IndexError):
        return 0


def children() -> list[tuple[str, int]]:
    """(name, rss in KiB) of every process whose parent is this one."""
    me = os.getpid()
    found: list[tuple[str, int]] = []
    for entry in Path("/proc").glob("[0-9]*"):
        status = _status(entry.name)
        if status.get("PPid", "").strip() == str(me):
            found.append((status.get("Name", "?").strip(), _kib(status, "VmRSS")))
    return found


def _cgroup() -> str:
    try:
        stat = dict(
            line.split()
            for line in (CGROUP / "memory.stat").read_text(encoding="utf-8").splitlines()
        )
        total = int((CGROUP / "memory.current").read_text(encoding="utf-8"))
        return (
            f"container={total // 2**20}MB anon={int(stat.get('anon', 0)) // 2**20}MB "
            f"file={int(stat.get('file', 0)) // 2**20}MB"
        )
    except (OSError, ValueError):
        return "container=n/a"


def report(previous: tracemalloc.Snapshot | None) -> tuple[str, tracemalloc.Snapshot | None]:
    """The log line, and the allocation snapshot to compare with next time."""
    own = _status(str(os.getpid()))
    kids = children()
    parts = [
        f"rss={_mb(_kib(own, 'VmRSS'))}",
        _cgroup(),
        f"threads={own.get('Threads', '?').strip()}",
        f"children={len(kids)}"
        + (f" ({', '.join(f'{n}:{_mb(r)}' for n, r in kids[:8])})" if kids else ""),
    ]
    snapshot = tracemalloc.take_snapshot() if tracemalloc.is_tracing() else None
    if snapshot is not None and previous is not None:
        growth = [
            f"{s.traceback[0].filename.split('marione/')[-1].split('site-packages/')[-1]}:"
            f"{s.traceback[0].lineno} +{s.size_diff / 1024:.0f}KB"
            for s in snapshot.compare_to(previous, "lineno")[:5]
            if s.size_diff > 50 * 1024
        ]
        if growth:
            parts.append("grew: " + "; ".join(growth))
    return " ".join(parts), snapshot


async def log_memory(interval: float = INTERVAL) -> None:
    """Run forever (cancel it to stop): one `report` line every `interval` seconds."""
    if os.environ.get("MARIONE_TRACE_MEMORY") == "1":  # off by default: tracing costs memory itself
        tracemalloc.start(3)
    snapshot: tracemalloc.Snapshot | None = None
    while True:
        await asyncio.sleep(interval)
        line, snapshot = await asyncio.to_thread(report, snapshot)
        logger.info("memory: %s", line)
