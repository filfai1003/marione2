"""The bot object: intents, which cogs to load, and syncing the slash commands to the server."""

import logging

import discord
from discord.ext import commands

from marione.agent.service import ChatAgent
from marione.bot.context import Services
from marione.bot.voice import VoicePlayer, load_opus

logger = logging.getLogger("marione")

EXTENSIONS = (
    "marione.bot.cogs.economy",
    "marione.bot.cogs.entrance",
    "marione.bot.cogs.roles",
    "marione.bot.cogs.agent",
    "marione.bot.cogs.commands",
)


class MarioneBot(commands.Bot):
    def __init__(self, services: Services, voice: VoicePlayer) -> None:
        intents = discord.Intents.default()
        intents.members = True  # to find members by name and see who is in voice
        intents.voice_states = True
        intents.message_content = True  # economy and the chat agent read messages
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.services = services
        self.guild_id = services.config.guild_id
        self.chat_agent: ChatAgent | None = None
        self.voice = voice

    async def setup_hook(self) -> None:
        load_opus()
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Slash commands synced on guild %s.", self.guild_id)

    async def on_ready(self) -> None:
        logger.info("Online as %s (id %s).", self.user, self.user.id if self.user else "?")
