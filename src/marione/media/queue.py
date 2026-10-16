"""The music queue: what is playing, what comes next, and the position in the song. Pure state;
time is passed in."""

from dataclasses import dataclass, field

from marione.media.ytdl import Track

MAX_QUEUE = 50


@dataclass(frozen=True)
class Entry:
    track: Track
    requested_by: int
    requester_name: str


@dataclass
class MusicQueue:
    current: Entry | None = None
    upcoming: list[Entry] = field(default_factory=list)
    paused: bool = False
    _started: float = 0.0  # when the current song started, minus the time spent paused
    _paused_at: float = 0.0

    def add(self, entry: Entry, *, now: bool = False) -> int:
        """Queue a song; returns its position (0 = it should start right away)."""
        if now or self.current is None:
            self.upcoming.insert(0, entry)
            return 0
        if len(self.upcoming) >= MAX_QUEUE:
            raise OverflowError("queue full")
        self.upcoming.append(entry)
        return len(self.upcoming)

    def advance(self, clock: float) -> Entry | None:
        """Move to the next song (None = nothing left)."""
        self.current = self.upcoming.pop(0) if self.upcoming else None
        self.paused = False
        self._started = clock
        return self.current

    def clear(self) -> None:
        self.current = None
        self.upcoming.clear()
        self.paused = False

    def remove(self, index: int) -> Entry | None:
        if 0 <= index < len(self.upcoming):
            return self.upcoming.pop(index)
        return None

    def pause(self, clock: float) -> None:
        if not self.paused:
            self.paused = True
            self._paused_at = clock

    def resume(self, clock: float) -> None:
        if self.paused:
            self._started += clock - self._paused_at
            self.paused = False

    def position(self, clock: float) -> float:
        if self.current is None:
            return 0.0
        end = self._paused_at if self.paused else clock
        return max(0.0, end - self._started)
