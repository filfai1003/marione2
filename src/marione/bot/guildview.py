"""The Discord side of the web page: members, voice presence, playing a sound, announcing."""

import logging
from collections.abc import Callable
from typing import Any

import discord

from marione.bot.voice import PlayStatus, VoicePlayer
from marione.ports import GuildMember, PlayOutcome

logger = logging.getLogger("marione.web")

_OUTCOMES = {
    PlayStatus.OK: PlayOutcome.OK,
    PlayStatus.BUSY: PlayOutcome.BUSY,
    PlayStatus.ERROR: PlayOutcome.ERROR,
}


def _to_member(m: discord.Member) -> GuildMember:
    return GuildMember(
        id=m.id,
        name=m.display_name,
        handle=m.name,
        avatar_url=str(m.display_avatar.url) if m.display_avatar else None,
        is_admin=m.guild_permissions.administrator,
        voice_channel=m.voice.channel.name if m.voice and m.voice.channel else None,
    )


class DiscordGuildView:
    def __init__(
        self,
        guild_getter: Callable[[], discord.Guild | None],
        voice: VoicePlayer,
        announce_channel_id: int = 0,
    ) -> None:
        self._guild = guild_getter
        self._voice = voice
        self._announce_channel_id = announce_channel_id

    def member(self, user_id: int) -> GuildMember | None:
        guild = self._guild()
        found = guild.get_member(user_id) if guild else None
        return _to_member(found) if found and not found.bot else None

    def members(self) -> list[GuildMember]:
        guild = self._guild()
        return [_to_member(m) for m in guild.members if not m.bot] if guild else []

    async def play_for(self, user_id: int, data: bytes, volume_pct: int) -> str:
        guild = self._guild()
        found = guild.get_member(user_id) if guild else None
        channel = found.voice.channel if found and found.voice else None
        if channel is None:
            return PlayOutcome.NOT_IN_VOICE
        status = await self._voice.play(channel, data, volume=volume_pct / 100)
        return _OUTCOMES[status]

    def voice_channel_of(self, user_id: int) -> Any:
        guild = self._guild()
        found = guild.get_member(user_id) if guild else None
        return found.voice.channel if found and found.voice else None

    def stop_audio(self) -> bool:
        return self._voice.stop()

    def channel_name(self, channel_id: int) -> str | None:
        guild = self._guild()
        channel = guild.get_channel(channel_id) if guild else None
        return f"#{channel.name}" if channel is not None else None

    async def announce(self, text: str) -> None:
        guild = self._guild()
        if guild is None:
            return
        channel = (
            guild.get_channel(self._announce_channel_id)
            if self._announce_channel_id
            else guild.system_channel
        )
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(text[:1900], allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            logger.warning("could not announce in #%s: %s", channel.name, exc)
