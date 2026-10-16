"""Entrance sounds: when a member joins a voice channel, the bot follows and plays their audio."""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands

from marione.bot.voice import entrance_source
from marione.domain.limits import PlayLimiter

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.entrance")


class EntranceCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot
        self._limiter = PlayLimiter(max_events=3, window_seconds=600)
        self._lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.guild.id != self.bot.guild_id:
            return
        if member.bot:
            return
        # Someone left a channel the bot is in: leave if only bots remain.
        if before.channel is not None and before.channel != after.channel:
            await self._leave_if_empty(member.guild, before.channel)
        joined = after.channel is not None and after.channel != before.channel
        if not joined or after.channel is None:
            return
        svc = self.bot.services
        if not await svc.settings.is_enabled("sound"):
            return
        if after.channel.name == svc.config.afk_channel_name:
            return  # nobody gets a fanfare for going to bed
        if not self._limiter.allow(member.id, time.monotonic()):
            return
        sound = await svc.sounds.pick_random(member.id)
        if sound is None:
            return
        async with self._lock:
            await self._play(member.guild, after.channel, sound.data)

    async def _play(
        self,
        guild: discord.Guild,
        channel: discord.VoiceChannel | discord.StageChannel,
        data: bytes,
    ) -> None:
        existing = guild.voice_client
        try:
            client: discord.VoiceClient
            if existing is None:
                client = await channel.connect()
            else:
                client = cast(discord.VoiceClient, existing)
            if client.channel != channel:
                if client.is_playing():
                    return  # busy in another channel: skip rather than cut it off
                await client.move_to(channel)
            if client.is_playing():
                return
            client.play(entrance_source(data))
        except (discord.ClientException, discord.HTTPException, TimeoutError) as exc:
            logger.warning("could not play the entrance sound: %s", exc)

    async def _leave_if_empty(
        self, guild: discord.Guild, channel: discord.VoiceChannel | discord.StageChannel
    ) -> None:
        client = guild.voice_client
        if client is None or client.channel != channel:
            return
        if all(m.bot for m in channel.members):
            await client.disconnect(force=False)


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(EntranceCog(bot))
