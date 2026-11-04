import asyncio
import contextlib
import logging
import tracemalloc

import pytest

from marione import watch


def test_the_report_never_fails_and_names_the_parts() -> None:
    line, snapshot = watch.report(None)
    assert "rss=" in line and "threads=" in line and "children=" in line and "container=" in line
    assert snapshot is None  # not tracing: no allocation comparison


def test_growth_is_reported_between_two_snapshots() -> None:
    tracemalloc.start(3)
    try:
        _, first = watch.report(None)
        hold = [bytes(1000) for _ in range(500)]  # ~500 KB that stays alive
        line, second = watch.report(first)
        assert first is not None and second is not None and hold
        assert "grew:" in line and "KB" in line
    finally:
        tracemalloc.stop()


async def test_the_loop_logs_every_interval(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="marione.memory"):
        task = asyncio.create_task(watch.log_memory(0.01))
        await asyncio.sleep(0.15)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        tracemalloc.stop()
    assert any(r.getMessage().startswith("memory: rss=") for r in caplog.records)
