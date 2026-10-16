"""Who is idle, who should go to the bed, who is paying for staying there.

The Discord cog feeds it voice-state changes and asks what to do; moving members around and the
temporary channel stay in the cog. Time is always passed in.
"""

from marione.domain.afk import VoiceFlags, is_away, is_due
from marione.domain.rules import EconomyRules


class AfkTracker:
    def __init__(self, rules: EconomyRules) -> None:
        self._rules = rules
        self._idle_since: dict[int, float] = {}
        self._bed_since: dict[int, float] = {}  # when the drain was last charged up to

    def observe(self, user_id: int, flags: VoiceFlags, now: float) -> None:
        """A member's voice state changed (or was checked)."""
        if user_id in self._bed_since:
            return  # already in bed: leaving is reported with `leave`
        if is_away(flags):
            self._idle_since.setdefault(user_id, now)
        else:
            self._idle_since.pop(user_id, None)

    def due(self, now: float) -> list[int]:
        """Members idle long enough to be moved to the bed."""
        return [
            uid
            for uid, since in self._idle_since.items()
            if is_due(since, now, self._rules.afk_idle_seconds)
        ]

    def enter_bed(self, user_id: int, now: float) -> None:
        self._idle_since.pop(user_id, None)
        self._bed_since[user_id] = now

    def in_bed(self, user_id: int) -> bool:
        return user_id in self._bed_since

    def leave(self, user_id: int) -> None:
        """The member left voice or the bed: forget everything about them."""
        self._idle_since.pop(user_id, None)
        self._bed_since.pop(user_id, None)

    def drain_due(self, now: float) -> list[tuple[int, int]]:
        """(member, whole minutes to charge) for everyone in bed. Each minute is charged once."""
        out: list[tuple[int, int]] = []
        for uid, charged_until in self._bed_since.items():
            minutes = int((now - charged_until) // 60)
            if minutes > 0:
                self._bed_since[uid] = charged_until + minutes * 60
                out.append((uid, minutes))
        return out
