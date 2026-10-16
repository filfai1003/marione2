"""Start-up: configuration, database, migrations, web server, then the bot (with restarts)."""

import asyncio
import logging
import sys
from dataclasses import dataclass

import asyncpg
import discord

from marione.bot.app import MarioneBot
from marione.bot.context import Services, build_services
from marione.bot.guildview import DiscordGuildView
from marione.bot.music import MusicPlayer
from marione.bot.voice import VoicePlayer, music_source
from marione.config import load_settings
from marione.db.pool import Pool, create_pool, migrate
from marione.web import app as web_app
from marione.web.deps import WebDeps

logger = logging.getLogger("marione")

RATE_LIMIT_BACKOFF = 900.0  # a Discord/Cloudflare ban lasts a while: do not keep poking it
CRASH_BACKOFF = 30.0


@dataclass(frozen=True)
class Restart:
    retry: bool
    delay: float = 0.0


def restart_policy(error: BaseException) -> Restart:
    """What to do when the bot stops with this error."""
    if isinstance(error, discord.LoginFailure | discord.PrivilegedIntentsRequired):
        return Restart(retry=False)  # a wrong token or a missing intent will not fix itself
    if isinstance(error, discord.HTTPException) and error.status == 429:
        return Restart(retry=True, delay=RATE_LIMIT_BACKOFF)
    return Restart(retry=True, delay=CRASH_BACKOFF)


async def _database_ok(pool: Pool) -> bool:
    try:
        return bool(await pool.fetchval("select 1") == 1)
    except (asyncpg.PostgresError, OSError):
        return False


async def run_bot(services: Services) -> int:
    """Run the bot until it stops for good. Returns the process exit code."""
    current: MarioneBot | None = None

    def guild() -> discord.Guild | None:
        return current.get_guild(services.config.guild_id) if current else None

    voice = VoicePlayer(guild)
    music = MusicPlayer(
        voice, services.ytdl, services.music, services.settings, source_factory=music_source
    )
    deps = WebDeps(
        services,
        DiscordGuildView(guild, voice, services.config.announce_channel_id),
        music=music,
    )
    runner = await web_app.start(
        web_app.create_app(
            deps,
            lambda: _database_ok(services.pool),
            lambda: current is not None and current.is_ready(),
        ),
        services.config.port,
    )
    presences = True
    try:
        while True:
            current = MarioneBot(services, voice, music, presences=presences)
            try:
                async with current:
                    await current.start(services.config.discord_token)
                return 0
            except discord.PrivilegedIntentsRequired as exc:
                if not presences:
                    logger.error("The bot stopped: %r", exc)
                    logger.error("Enable Server Members and Message Content in the portal.")
                    return 1
                presences = False
                logger.warning(
                    "The Presence intent is off in the Discord Developer Portal: starting without "
                    "online status and games. Enable it to let Marione learn members' habits."
                )
            except (discord.DiscordException, OSError, TimeoutError) as exc:
                policy = restart_policy(exc)
                logger.error("The bot stopped: %r", exc)
                if not policy.retry:
                    logger.error("Not retrying: fix the token or the intents and redeploy.")
                    return 1
                logger.info("Restarting in %.0f seconds.", policy.delay)
                await asyncio.sleep(policy.delay)
    finally:
        await runner.cleanup()
        await deps.http.aclose()


async def run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,  # Railway marks everything on stderr as an error
    )
    config = load_settings()
    pool = await create_pool(config.database_url)
    try:
        applied = await migrate(pool, config.migrations_dir)
        if applied:
            logger.info("Applied migrations: %s", ", ".join(applied))
        services = build_services(config, pool)
        try:
            return await run_bot(services)
        finally:
            if services.openrouter is not None:
                await services.openrouter.aclose()
    finally:
        await pool.close()


def main() -> None:
    sys.exit(asyncio.run(run()))
