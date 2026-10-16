"""Entrance sounds: when a member joins a voice channel, the bot follows and plays their audio."""

import logging
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from marione.domain.limits import PlayLimiter

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.entrance")


class EntranceCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot
        self._limiter = PlayLimiter(max_events=3, window_seconds=600)

    async def cog_load(self) -> None:
        self.reaper.start()

    async def cog_unload(self) -> None:
        self.reaper.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.guild.id != self.bot.guild_id or member.bot:
            return
        # Someone left a channel the bot is in: leave if only bots remain.
        if before.channel is not None and before.channel != after.channel:
            await self.bot.voice.leave_if_empty(before.channel)
        joined = after.channel is not None and after.channel != before.channel
        if not joined or after.channel is None:
            return
        svc = self.bot.services
        if not await svc.settings.is_enabled("sound"):
            return
        if not self._limiter.allow(member.id, time.monotonic()):
            return
        sound = await svc.sounds.pick_random(member.id)
        if sound is None:
            return
        volume = await svc.settings.soundboard_volume() / 100
        # An entrance never cuts off a sound that is already playing.
        await self.bot.voice.play(after.channel, sound.data, volume=volume, interrupt=False)

    @tasks.loop(seconds=30)
    async def reaper(self) -> None:
        await self.bot.voice.reap_idle()

    @reaper.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(EntranceCog(bot))
