"""A sliding-window limit: at most N events per member within a time window."""

from collections import deque


class PlayLimiter:
    def __init__(self, max_events: int, window_seconds: float) -> None:
        self._max = max_events
        self._window = window_seconds
        self._events: dict[int, deque[float]] = {}

    def allow(self, user_id: int, now: float) -> bool:
        """Record the event and say whether it is within the limit."""
        events = self._events.setdefault(user_id, deque())
        while events and now - events[0] >= self._window:
            events.popleft()
        if len(events) >= self._max:
            return False
        events.append(now)
        return True
