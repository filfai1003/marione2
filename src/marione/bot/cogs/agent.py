"""Marione's chat brain, wired to Discord: messages in, one reply out."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from marione.agent.service import AgentConfig, ChatAgent
from marione.bot.adapters import DiscordWorld, GuildDirectory, format_reply, to_chat_message
from marione.clock import SystemClock
from marione.domain.triggers import compile_trigger
from marione.llm.types import LLMError

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.agent")

TRIGGER_WORDS = ("marione", "marioncelli")


class AgentCog(commands.Cog):
    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot
        self._triggers = [compile_trigger(w) for w in TRIGGER_WORDS]
        self.agent: ChatAgent | None = None

    async def cog_load(self) -> None:
        svc = self.bot.services
        if svc.llm is None or self.bot.user is None:
            logger.info("The AI is off (no OPENROUTER_API_KEY): Marione will not chat.")
            return
        cfg = svc.config
        self.agent = ChatAgent(
            llm=svc.llm,
            ledger=svc.ledger,
            memory=svc.memory,
            settings=svc.settings,
            directory=GuildDirectory(lambda: self.bot.get_guild(self.bot.guild_id)),
            config=AgentConfig(
                model=cfg.agent_model,
                gate_model=cfg.agent_gate_model,
                fallbacks=cfg.fallback_models,
            ),
            bot_id=self.bot.user.id,
            bot_name=self._bot_name,
            clock=SystemClock(),
            rules=svc.agent_rules,
            chatlog=svc.chatlog,
            world=DiscordWorld(
                lambda: self.bot.get_guild(self.bot.guild_id),
                ZoneInfo(cfg.timezone),
                lambda: datetime.now(UTC),
            ),
        )
        self.bot.chat_agent = self.agent
        self.maintenance_loop.start()

    async def cog_unload(self) -> None:
        self.maintenance_loop.cancel()
        self.bot.chat_agent = None

    def _bot_name(self) -> str:
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is not None and guild.me is not None:
            return str(guild.me.display_name)
        return "Marione"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        agent = self.agent
        if agent is None or message.author.bot or message.guild is None:
            return
        if message.guild.id != self.bot.guild_id or not message.content.strip():
            return
        chat = to_chat_message(message, self.bot.user.id if self.bot.user else 0, self._triggers)
        try:
            reply = await agent.handle(chat)
        except LLMError as exc:  # pragma: no cover - the agent already absorbs these
            logger.warning("agent error: %s", exc)
            return
        if reply is None:
            return
        text = format_reply(reply, self._bot_name())
        if not text:
            return
        try:
            await message.reply(text[:1900], mention_author=False)
        except discord.HTTPException:
            try:
                await message.channel.send(text[:1900])
            except discord.HTTPException as exc:
                logger.warning("could not send the reply: %s", exc)

    @tasks.loop(seconds=60)
    async def maintenance_loop(self) -> None:
        if self.agent is not None:
            await self.agent.maintenance()

    @maintenance_loop.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(AgentCog(bot))
