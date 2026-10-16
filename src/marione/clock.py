"""The real clock, behind the small interface the services take (so tests can pass their own)."""

import time
from datetime import UTC, datetime


class SystemClock:
    def mono(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)
