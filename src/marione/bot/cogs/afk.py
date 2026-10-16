"""Auto-AFK: a member idle for too long is moved to a private "bed" channel, which costs a one-off
fine plus a drain per minute. Needs Move Members, Mute Members and Manage Channels."""

import logging
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from marione.bot.cogs.economy import voice_flags

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.afk")


class AfkCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot
        self._bed_id: int | None = None

    async def cog_load(self) -> None:
        if self.bot.services.economy_rules.afk_idle_seconds > 0:
            self.check_loop.start()
            self.drain_loop.start()

    async def cog_unload(self) -> None:
        self.check_loop.cancel()
        self.drain_loop.cancel()

    async def _enabled(self) -> bool:
        return await self.bot.services.settings.is_enabled("afk")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot or member.guild.id != self.bot.guild_id:
            return
        afk = self.bot.services.afk
        if after.channel is None:
            afk.leave(member.id)
        elif (
            self._bed_id is not None and after.channel.id != self._bed_id and afk.in_bed(member.id)
        ):
            afk.leave(member.id)  # the member left the bed on their own
        elif after.channel.id != self._bed_id:
            afk.observe(member.id, voice_flags(after), time.monotonic())
        await self._remove_bed_if_empty(member.guild)

    async def _bed(self, guild: discord.Guild) -> discord.VoiceChannel | None:
        name = self.bot.services.config.afk_channel_name
        if self._bed_id is not None:
            existing = guild.get_channel(self._bed_id)
            if isinstance(existing, discord.VoiceChannel):
                return existing
            self._bed_id = None
        overwrites: Mapping[
            discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
        ] = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False, connect=False, speak=False
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, connect=True, move_members=True, mute_members=True
            ),
        }
        try:
            channel = await guild.create_voice_channel(
                name, overwrites=overwrites, reason="Marione: auto-AFK"
            )
        except discord.Forbidden:
            logger.error("Cannot create the AFK channel: give Marione 'Manage Channels'.")
            return None
        self._bed_id = channel.id
        return channel

    async def _remove_bed_if_empty(self, guild: discord.Guild) -> None:
        if self._bed_id is None:
            return
        channel = guild.get_channel(self._bed_id)
        if isinstance(channel, discord.VoiceChannel) and not channel.members:
            try:
                await channel.delete(reason="Marione: the AFK bed is empty")
            except discord.HTTPException as exc:
                logger.warning("could not delete the AFK channel: %s", exc)
                return
            self._bed_id = None

    @tasks.loop(seconds=15)
    async def check_loop(self) -> None:
        svc = self.bot.services
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is None or not await self._enabled():
            return
        now = time.monotonic()
        for uid in svc.afk.due(now):
            member = guild.get_member(uid)
            if member is None or member.voice is None or member.voice.channel is None:
                svc.afk.leave(uid)
                continue
            bed = await self._bed(guild)
            if bed is None:
                return
            try:
                await member.move_to(bed, reason="Marione: auto-AFK")
            except discord.HTTPException as exc:
                logger.warning("could not move %s to bed: %s", member, exc)
                continue
            svc.afk.enter_bed(uid, now)
            fined = await svc.economy.afk_fine(uid, key=f"afk:{uid}:{int(time.time())}")
            if fined and bed.guild.system_channel:
                await bed.guild.system_channel.send(
                    f"😴 {member.display_name} a letto: -{fined}", silent=True
                )

    @tasks.loop(seconds=60)
    async def drain_loop(self) -> None:
        svc = self.bot.services
        if not await self._enabled():
            return
        now = time.monotonic()
        for uid, minutes in svc.afk.drain_due(now):
            await svc.economy.afk_drain(uid, minutes, key=f"drain:{uid}:{int(time.time())}")

    @check_loop.before_loop
    @drain_loop.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(AfkCog(bot))
