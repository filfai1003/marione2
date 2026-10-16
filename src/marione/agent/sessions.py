"""Short-term memory: the live window of each channel. Time is always passed in."""

from dataclasses import dataclass, field

from marione.agent.prompt import Line


@dataclass
class Session:
    channel_id: int
    opened: float
    last_activity: float
    window: list[Line] = field(default_factory=list)
    last_bot_reply: float = 0.0
    msgs_since_bot: int = 0
    spoke: bool = False
    compacting: bool = False

    def add(self, line: Line, now: float) -> None:
        self.window.append(line)
        self.last_activity = now
        self.msgs_since_bot += 1

    def note_bot_reply(self, now: float) -> None:
        self.last_bot_reply = now
        self.msgs_since_bot = 0
        self.spoke = True

    def in_followup(self, now: float, window_seconds: float, max_msgs: int) -> bool:
        """The bot spoke here a moment ago and people are still talking to it."""
        return (
            self.spoke
            and now - self.last_bot_reply < window_seconds
            and self.msgs_since_bot <= max_msgs
        )

    def history(self) -> list[Line]:
        """Everything before the current (last) message."""
        return self.window[:-1]

    def needs_compaction(self, compact_at: int, token_limit: int) -> bool:
        if self.compacting:
            return False
        if len(self.window) > compact_at:
            return True
        return sum(len(m.text) for m in self.window) // 4 > token_limit

    def old_for_compaction(self, keep: int) -> list[Line]:
        return self.window[:-keep] if len(self.window) > keep else []

    def apply_compaction(self, consumed: int) -> None:
        """Drop exactly the messages that were summarised: newer ones added meanwhile stay."""
        self.window = self.window[consumed:]
        self.compacting = False

    def trim_hard(self, limit: int) -> None:
        """A safety net so memory stays bounded even if summarising keeps failing."""
        if len(self.window) > limit:
            self.window = self.window[-limit:]

    def is_idle(self, now: float, idle_seconds: float) -> bool:
        return now - self.last_activity >= idle_seconds

    def participants(self) -> list[int]:
        seen: list[int] = []
        for line in self.window:
            if line.author_id not in seen:
                seen.append(line.author_id)
        return seen


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[int, Session] = {}

    def get(self, channel_id: int, now: float) -> Session:
        session = self._sessions.get(channel_id)
        if session is None:
            session = self._sessions[channel_id] = Session(channel_id, now, now)
        return session

    def find(self, channel_id: int) -> Session | None:
        return self._sessions.get(channel_id)

    def all(self) -> list[Session]:
        return list(self._sessions.values())

    def close(self, channel_id: int) -> Session | None:
        return self._sessions.pop(channel_id, None)
