"""Earning by chatting and by being active in voice; the public penalty for spam."""

import logging
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from marione.bot.adapters import unit
from marione.domain.spam import Verdict
from marione.domain.voice import VoiceFlags, is_away

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.economy")


def voice_flags(state: discord.VoiceState) -> VoiceFlags:
    return VoiceFlags(state.self_mute, state.self_deaf, state.mute, state.deaf)


class EconomyCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.voice_loop.start()

    async def cog_unload(self) -> None:
        self.voice_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or message.guild.id != self.bot.guild_id:
            return
        svc = self.bot.services
        if not await svc.settings.is_enabled("economy"):
            return
        outcome = await svc.economy.on_message(
            message.author.id,
            message.author.display_name,
            message.clean_content,
            now=time.monotonic(),
            message_id=message.id,
        )
        if outcome.verdict is Verdict.SPAM and outcome.amount > 0:
            await message.reply(
                f"💸 spam: **-{outcome.amount} {unit(outcome.amount)}** per "
                f"{message.author.display_name}",
                mention_author=False,
            )

    @tasks.loop(seconds=60)
    async def voice_loop(self) -> None:
        """Every minute, pay the members who are really there (not muted/deafened, not in bed)."""
        svc = self.bot.services
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is None or not await svc.settings.is_enabled("economy"):
            return
        active: list[int] = []
        for channel in guild.voice_channels:
            for member in channel.members:
                if member.bot:
                    continue
                if member.voice is not None and not is_away(voice_flags(member.voice)):
                    await svc.ledger.remember_name(member.id, member.display_name)
                    active.append(member.id)
        if active:
            await svc.economy.voice_tick(active, minute=int(time.time() // 60))

    @voice_loop.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(EconomyCog(bot))
