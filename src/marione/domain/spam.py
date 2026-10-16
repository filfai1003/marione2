"""Deterministic decision for each chat message: earn, ignore, or spam.

A small state machine that gets the time as an argument, so it needs no clock to be tested.
Earning is rate-limited per member (chatting fast cannot be farmed). Spam is a burst of
messages or the same message repeated; it is penalised at most once per penalty cooldown, so a
flood costs one penalty and not one per message.
"""

from collections import deque
from enum import StrEnum

from marione.domain.rules import EconomyRules


class Verdict(StrEnum):
    EARN = "earn"
    IGNORE = "ignore"
    SPAM = "spam"


class SpamTracker:
    def __init__(self, rules: EconomyRules) -> None:
        self._rules = rules
        self._times: dict[int, deque[float]] = {}
        self._last_text: dict[int, tuple[str, int]] = {}
        self._last_earn: dict[int, float] = {}
        self._last_penalty: dict[int, float] = {}

    def register(self, user_id: int, text: str, now: float) -> Verdict:
        r = self._rules
        norm = text.strip().lower()

        recent = self._times.setdefault(user_id, deque())
        recent.append(now)
        while recent and now - recent[0] > r.spam_window_seconds:
            recent.popleft()

        previous, count = self._last_text.get(user_id, ("", 0))
        count = count + 1 if norm and norm == previous else 1
        self._last_text[user_id] = (norm, count)

        flooding = len(recent) > r.spam_max_burst
        repeating = bool(norm) and count >= r.spam_repeat
        if flooding or repeating:
            last = self._last_penalty.get(user_id)
            if last is None or now - last >= r.spam_penalty_cooldown_seconds:
                self._last_penalty[user_id] = now
                return Verdict.SPAM
            return Verdict.IGNORE

        if len(norm) < r.message_min_chars:
            return Verdict.IGNORE
        last_earn = self._last_earn.get(user_id)
        if last_earn is not None and now - last_earn < r.message_cooldown_seconds:
            return Verdict.IGNORE
        self._last_earn[user_id] = now
        return Verdict.EARN


def spam_fine(balance: int, rules: EconomyRules) -> int:
    """The percentage penalty, at least the minimum, never more than the member has."""
    pct = balance * rules.spam_penalty_pct // 100
    return min(balance, max(rules.spam_penalty_min, pct))
