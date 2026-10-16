"""Uploading and managing sounds: the checks shared by the slash commands and the web page."""

from dataclasses import dataclass

from marione import audio
from marione.db.soundboard import MAX_DURATION_MS, BoardSound, SoundboardRepo
from marione.db.sounds import SoundError, SoundsRepo

ENTRANCE_MAX_MS = 15_000


@dataclass(frozen=True)
class SoundService:
    board: SoundboardRepo
    entrances: SoundsRepo

    async def add_to_board(self, creator_id: int, name: str, emoji: str, data: bytes) -> int:
        content_type, duration = await audio.inspect(data, max_ms=MAX_DURATION_MS)
        return await self.board.add(creator_id, name, emoji, content_type, data, duration)

    async def add_entrance(self, user_id: int, name: str, data: bytes) -> None:
        content_type, duration = await audio.inspect(data, max_ms=ENTRANCE_MAX_MS)
        await self.entrances.add(user_id, name, content_type, data, duration)

    @staticmethod
    def may_modify(sound: BoardSound, user_id: int, *, is_admin: bool) -> bool:
        """Only the creator (or an administrator) can rename or delete a board sound."""
        return is_admin or sound.creator_id == user_id


__all__ = ["ENTRANCE_MAX_MS", "SoundError", "SoundService"]
