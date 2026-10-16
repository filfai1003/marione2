"""What the web page needs from Discord, as plain types, so it never imports discord.py and can
be run (and tested) against a fake server."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GuildMember:
    id: int
    name: str  # display name in the server
    handle: str  # the account's username
    avatar_url: str | None
    is_admin: bool
    voice_channel: str | None  # name of the voice channel they are in, if any


class PlayOutcome:
    OK = "ok"
    NOT_IN_VOICE = "not_in_voice"
    BUSY = "busy"
    ERROR = "error"


class GuildView(Protocol):
    def member(self, user_id: int) -> GuildMember | None:
        """A member of the server, or None if they are not in it."""
        ...

    def members(self) -> list[GuildMember]:
        """Every human member."""
        ...

    async def play_for(self, user_id: int, data: bytes, volume_pct: int) -> str:
        """Play `data` in the voice channel where `user_id` is (a PlayOutcome value)."""
        ...

    def stop_audio(self) -> bool: ...

    async def announce(self, text: str) -> None:
        """Post a public line in the server (a heist result, say)."""
        ...
