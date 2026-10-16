"""Voice presence and entrance sounds: the bot joins as soon as somebody enters a voice channel,
stays until it is alone, and plays the member's entrance sound when they arrive."""

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
        moved = before.channel != after.channel
        if not moved:
            return  # a mute or a deafen, not a change of channel
        # Follow the people: join whoever just came in, leave when nobody is left.
        await self.bot.voice.settle(joined=after.channel)
        if after.channel is None:
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
        # An entrance never cuts off a sound and never pulls the bot away from other people.
        await self.bot.voice.play(
            after.channel, sound.data, volume=volume, interrupt=False, move=False
        )

    @tasks.loop(seconds=60)
    async def reaper(self) -> None:
        """A safety net for missed events (and the start): be where the people are."""
        await self.bot.voice.settle()

    @reaper.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(EntranceCog(bot))
