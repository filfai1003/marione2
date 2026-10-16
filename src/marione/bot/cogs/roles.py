"""Wealth roles: every few minutes each member gets the server role of their tier.

Marione only ever touches the roles it created itself (their ids are stored in the database), never
a role someone else made with the same name. The feature is off until an admin switches it on,
because it creates roles in the server.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from marione.domain.roles import TIERS, plan_changes

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.roles")

MAX_CHANGES_PER_RUN = 40  # Discord rate limits: a big backlog is worked off over several runs
PAUSE_SECONDS = 0.6


class RolesCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot
        self._warned = False

    async def cog_load(self) -> None:
        self.loop.start()

    async def cog_unload(self) -> None:
        self.loop.cancel()

    @tasks.loop(minutes=5)
    async def loop(self) -> None:
        guild = self.bot.get_guild(self.bot.guild_id)
        svc = self.bot.services
        if guild is None or not await svc.settings.is_enabled("roles"):
            return
        if not guild.me.guild_permissions.manage_roles:
            if not self._warned:
                logger.warning("Wealth roles are on but Marione lacks 'Manage Roles'.")
                self._warned = True
            return
        self._warned = False
        try:
            await self.reconcile(guild)
        except discord.Forbidden:
            logger.warning("Cannot manage the wealth roles: put Marione's role above them.")
        except discord.HTTPException as exc:
            logger.warning("Wealth roles update failed, will retry: %s", exc)

    @loop.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()

    async def ensure_roles(self, guild: discord.Guild) -> dict[str, discord.Role]:
        """The role of every tier, creating the ones that are missing (or were deleted)."""
        stored = await self.bot.services.roles.all()
        roles: dict[str, discord.Role] = {}
        for tier in TIERS:
            role = guild.get_role(stored.get(tier.key, 0))
            if role is None:
                role = await guild.create_role(
                    name=tier.name,
                    colour=discord.Colour(tier.color),
                    reason="Marione: wealth role",
                )
                await self.bot.services.roles.set(tier.key, role.id)
            roles[tier.key] = role
        return roles

    async def reconcile(self, guild: discord.Guild) -> int:
        """Give each member exactly the role of their tier. Returns how many members changed."""
        svc = self.bot.services
        roles = await self.ensure_roles(guild)
        by_id = {role.id: key for key, role in roles.items()}
        balances = await svc.ledger.balances()
        held: dict[int, set[str]] = {}
        for member in guild.members:
            if member.bot:
                continue
            keys = {by_id[r.id] for r in member.roles if r.id in by_id}
            if keys:
                held[member.id] = keys
        present = {m.id for m in guild.members if not m.bot}
        balances = {uid: bal for uid, bal in balances.items() if uid in present}
        changes = plan_changes(balances, held, min_balance=svc.economy_rules.role_min_balance)
        done = 0
        for change in changes[:MAX_CHANGES_PER_RUN]:
            target = guild.get_member(change.user_id)
            if target is None:
                continue
            if change.remove:
                await target.remove_roles(
                    *[roles[k] for k in change.remove], reason="Marione: wealth role"
                )
            if change.add:
                await target.add_roles(roles[change.add], reason="Marione: wealth role")
            done += 1
            await asyncio.sleep(PAUSE_SECONDS)
        if done:
            logger.info("Updated wealth roles for %d member(s).", done)
        return done


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(RolesCog(bot))
