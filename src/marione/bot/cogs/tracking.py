"""Watching the server to learn members' habits: when they are online, in voice, what they play,
when they write. Only counts and spans are stored (never message text here), 90 days at most, and
`/marione forget` erases them. Switched off with the "habits" feature.

Online status and games need Discord's Presence intent; without it only voice and messages are
recorded.
"""

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.habits")

STATUSES = {"online": "online", "idle": "idle", "dnd": "dnd", "do_not_disturb": "dnd"}
KINDS = {
    discord.ActivityType.playing: "playing",
    discord.ActivityType.streaming: "streaming",
    discord.ActivityType.listening: "listening",
    discord.ActivityType.watching: "watching",
    discord.ActivityType.competing: "competing",
}


def status_of(member: discord.Member) -> str | None:
    return STATUSES.get(str(member.status))


def activities_of(member: discord.Member) -> list[tuple[str, str, str | None]]:
    out: list[tuple[str, str, str | None]] = []
    for activity in member.activities:
        if isinstance(activity, discord.Spotify):
            out.append(("listening", "Spotify", f"{activity.artist} – {activity.title}"[:200]))
            continue
        if isinstance(activity, discord.CustomActivity) or not activity.name:
            continue
        kind = KINDS.get(activity.type)
        if kind is None:
            continue
        details = getattr(activity, "details", None)
        out.append((kind, activity.name, details if isinstance(details, str) else None))
    return out


class TrackingCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot
        self._on = True
        self._checked = 0.0
        self._started = False

    async def cog_load(self) -> None:
        self.housekeeping.start()

    async def cog_unload(self) -> None:
        self.housekeeping.cancel()

    async def enabled(self) -> bool:
        """The feature switch, read at most once a minute (presence events are frequent)."""
        if time.monotonic() - self._checked > 60:
            self._on = await self.bot.services.settings.is_enabled("habits")
            self._checked = time.monotonic()
        return self._on

    def _ours(self, guild: discord.Guild | None) -> bool:
        return guild is not None and guild.id == self.bot.guild_id

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._started:
            return
        self._started = True
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is None or not await self.enabled():
            return
        habits = self.bot.services.habits
        await habits.close_all()  # whatever was open before the restart is unknown now
        presences = self.bot.intents.presences
        for member in guild.members:
            if member.bot:
                continue
            await self.bot.services.ledger.remember_name(member.id, member.display_name)
            if presences:
                await habits.set_presence(member.id, status_of(member))
                await habits.set_activities(member.id, activities_of(member))
            channel = member.voice.channel if member.voice else None
            if channel is not None:
                await habits.set_voice(member.id, channel.id, channel.name)
        logger.info("Habits: tracking %s (presence %s).", guild.name, "on" if presences else "off")

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot or not self._ours(after.guild) or not await self.enabled():
            return
        habits = self.bot.services.habits
        if status_of(before) != status_of(after):
            await habits.set_presence(after.id, status_of(after))
        if activities_of(before) != activities_of(after):
            await habits.set_activities(after.id, activities_of(after))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot or not self._ours(member.guild) or before.channel == after.channel:
            return
        if not await self.enabled():
            return
        channel = after.channel
        await self.bot.services.ledger.remember_name(member.id, member.display_name)
        await self.bot.services.habits.set_voice(
            member.id, channel.id if channel else None, channel.name if channel else ""
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not self._ours(message.guild) or not await self.enabled():
            return
        tz = ZoneInfo(self.bot.services.config.timezone)
        await self.bot.services.habits.count_message(
            message.author.id, datetime.now(UTC).astimezone(tz)
        )

    @tasks.loop(hours=6)
    async def housekeeping(self) -> None:
        await self.bot.services.habits.trim()

    @housekeeping.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(TrackingCog(bot))
