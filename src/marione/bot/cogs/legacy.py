"""Bring over the old Marione's data (balances, soundboard, entrance sounds, favourites, roles).

It runs by itself once, the first time the new bot starts, and an admin can run it again with
/marione-admin importa-vecchio (nothing is imported twice). The old channel is only read.
"""

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands

from marione.services.legacy import ImportReport, LegacyImporter, LegacyMessage

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.legacy")

CHANNEL_NAME = "marione-data"
DONE_KEY = "legacy:auto_import_done"


class LegacyCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot
        self._started = False

    def channel(self) -> discord.TextChannel | None:
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is None:
            return None
        found = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
        return found if isinstance(found, discord.TextChannel) else None

    async def run(self) -> ImportReport | None:
        channel = self.channel()
        if channel is None:
            return None
        svc = self.bot.services
        importer = LegacyImporter(svc.pool, svc.ledger, svc.soundboard, svc.sounds)

        async def history() -> AsyncIterator[LegacyMessage]:
            async for msg in channel.history(limit=None, oldest_first=True):
                yield cast(LegacyMessage, msg)

        report = await importer.run(history())
        await self.adopt_roles(channel.guild, report)
        return report

    async def adopt_roles(self, guild: discord.Guild, report: ImportReport) -> None:
        """Keep the old bot's wealth roles (members already have them) instead of new copies."""
        repo = self.bot.services.roles
        mine = await repo.all()
        for key, old_id in report.old_roles.items():
            old = guild.get_role(old_id)
            if old is None:
                continue
            duplicate = guild.get_role(mine.get(key, 0))
            if duplicate is not None and duplicate.id != old.id:
                try:
                    await duplicate.delete(reason="Marione: keeping the old wealth role")
                except discord.HTTPException as exc:
                    logger.warning("could not delete the duplicate role %s: %s", key, exc)
            await repo.set(key, old.id)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._started:
            return
        self._started = True
        settings = self.bot.services.settings
        if await settings.get_value(DONE_KEY):
            return
        try:
            report = await self.run()
        except discord.HTTPException as exc:
            logger.warning("legacy import failed, it can be retried: %s", exc)
            return
        if report is None:
            logger.info("No #%s channel: nothing to import from the old Marione.", CHANNEL_NAME)
        await settings.set_value(DONE_KEY, True)


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(LegacyCog(bot))
