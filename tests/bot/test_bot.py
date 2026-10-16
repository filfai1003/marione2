import re
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import discord
import pytest

from marione.agent.types import ActionRecord, MemberRef, Reply
from marione.bot.adapters import GuildDirectory, action_headline, format_reply, to_chat_message
from marione.bot.app import EXTENSIONS, MarioneBot
from marione.bot.context import build_services
from marione.bot.voice import VoicePlayer
from marione.config import Settings
from marione.db.pool import Pool
from marione.domain.triggers import compile_trigger
from marione.main import CRASH_BACKOFF, RATE_LIMIT_BACKOFF, restart_policy

BOT = 999
TRIGGERS = [compile_trigger("marione")]


def user(uid: int, name: str, bot: bool = False) -> Any:
    return SimpleNamespace(id=uid, display_name=name, name=name.lower(), bot=bot)


def discord_message(
    text: str,
    *,
    mentions: list[Any] | None = None,
    reference: Any = None,
    attachments: list[Any] | None = None,
) -> Any:
    return SimpleNamespace(
        id=77,
        content=text,
        clean_content=text,
        author=user(1, "Anna"),
        channel=SimpleNamespace(id=10, name="general"),
        mentions=mentions or [],
        reference=reference,
        attachments=attachments or [],
    )


class TestToChatMessage:
    def test_plain_message_is_not_addressed(self) -> None:
        msg = to_chat_message(discord_message("buongiorno"), BOT, TRIGGERS)
        assert (msg.author_id, msg.author_name, msg.channel_id, msg.message_id) == (
            1,
            "Anna",
            10,
            77,
        )
        assert not msg.addressed and msg.mentioned_ids == ()

    def test_mention_name_and_reply_all_address_the_bot(self) -> None:
        mention = discord_message("ehi", mentions=[user(BOT, "Marione", bot=True)])
        assert to_chat_message(mention, BOT, TRIGGERS).addressed
        assert to_chat_message(discord_message("m4r10n3 vieni"), BOT, TRIGGERS).addressed
        ref = SimpleNamespace(resolved=SimpleNamespace(author=user(BOT, "Marione", bot=True)))
        reply = to_chat_message(discord_message("boh", reference=ref), BOT, TRIGGERS)
        assert reply.addressed and reply.reply_to_id == BOT

    def test_the_quoted_message_and_attachments_travel_with_it(self) -> None:
        resolved = SimpleNamespace(
            id=55, author=user(2, "Bruno"), clean_content="la pasta si spezza"
        )
        photo = SimpleNamespace(content_type="image/png", filename="gatto.png")
        msg = to_chat_message(
            discord_message(
                "no", reference=SimpleNamespace(resolved=resolved), attachments=[photo]
            ),
            BOT,
            TRIGGERS,
        )
        assert (msg.reply_to_message_id, msg.reply_author) == (55, "Bruno")
        assert msg.reply_text == "la pasta si spezza"
        assert msg.attachments == ("image: gatto.png",) and msg.channel_name == "general"

    def test_reply_to_someone_else_records_who_but_does_not_address(self) -> None:
        ref = SimpleNamespace(resolved=SimpleNamespace(author=user(2, "Bruno")))
        msg = to_chat_message(discord_message("hai ragione", reference=ref), BOT, TRIGGERS)
        assert msg.reply_to_id == 2 and not msg.addressed

    def test_other_mentions_are_listed_without_the_bot(self) -> None:
        mentions = [user(2, "Bruno"), user(BOT, "Marione", bot=True)]
        msg = to_chat_message(discord_message("@Bruno @Marione", mentions=mentions), BOT, TRIGGERS)
        assert msg.mentioned_ids == (2,)


class TestFormatReply:
    TARGET = MemberRef(2, "Bruno")

    def action(self, kind: str, amount: int, comment: str = "bravo") -> ActionRecord:
        return ActionRecord(kind, self.TARGET, amount, uuid4(), comment)

    def test_text_only(self) -> None:
        assert format_reply(Reply("vabbè"), "Marione") == "vabbè"

    def test_one_action_with_text(self) -> None:
        out = format_reply(Reply("ti sta bene", [self.action("fine", 30)]), "Marione")
        assert out == "⚖️ **Marione** multa **Bruno** di **30 Marioncelli** — ti sta bene"

    def test_gift_uses_singular_for_one_coin(self) -> None:
        out = format_reply(Reply("eh", [self.action("gift", 1)]), "Marione")
        assert out == "🎁 **Marione** regala **1 Marioncello** a **Bruno** — eh"

    def test_action_without_text_falls_back_to_the_tool_comment(self) -> None:
        out = format_reply(Reply(None, [self.action("fine", 5, "zitto")]), "Marione")
        assert out.endswith("— zitto")

    def test_headline_only_for_an_empty_line(self) -> None:
        assert (
            action_headline(self.action("fine", 2), "M")
            == "⚖️ **M** multa **Bruno** di **2 Marioncelli**"
        )


class TestGuildDirectory:
    def guild(self) -> Any:
        members = [
            user(1, "Anna"),
            user(2, "Bruno"),
            user(3, "Brunella"),
            user(4, "Robot", bot=True),
        ]
        return SimpleNamespace(members=members)

    def test_exact_name_wins_over_partial(self) -> None:
        d = GuildDirectory(self.guild)
        assert d.resolve("bruno") == MemberRef(2, "Bruno")

    def test_ambiguous_partial_name_resolves_to_nobody(self) -> None:
        assert GuildDirectory(self.guild).resolve("brun") is None

    def test_unique_partial_name_and_unknown_and_bots(self) -> None:
        d = GuildDirectory(self.guild)
        assert d.resolve("ann") == MemberRef(1, "Anna")
        assert d.resolve("nessuno") is None
        assert d.resolve("robot") is None
        assert d.resolve("  ") is None

    def test_no_guild_yet(self) -> None:
        assert GuildDirectory(lambda: None).resolve("anna") is None


class TestRestartPolicy:
    def test_bad_token_or_intents_never_retry(self) -> None:
        assert not restart_policy(discord.LoginFailure("bad")).retry
        assert not restart_policy(discord.PrivilegedIntentsRequired(None)).retry

    def test_rate_limit_backs_off_for_a_long_time(self) -> None:
        response = SimpleNamespace(status=429, reason="Too Many Requests")
        error = discord.HTTPException(response, "slow down")
        policy = restart_policy(error)
        assert policy.retry and policy.delay == RATE_LIMIT_BACKOFF

    def test_other_failures_retry_soon(self) -> None:
        policy = restart_policy(OSError("network"))
        assert policy.retry and policy.delay == CRASH_BACKOFF


def test_settings_parse_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.setenv("GUILD_ID", "123")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("AGENT_FALLBACK_MODELS", "a/b, c/d ,")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk")
    settings = Settings(_env_file=None)
    assert settings.guild_id == 123
    assert settings.fallback_models == ["a/b", "c/d"]
    assert settings.ai_enabled
    assert settings.migrations_dir.name == "migrations"


def test_missing_required_settings_fail_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DISCORD_TOKEN", "GUILD_ID", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="discord_token"):
        Settings(_env_file=None)


async def test_every_cog_loads_with_real_services_and_no_discord_connection(
    pool: Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The smoke test: wiring, imports, slash command registration. No token is ever used."""
    config = Settings(
        _env_file=None,
        discord_token="x",
        guild_id=1,
        database_url="postgresql://unused",
        openrouter_api_key="",
    )
    bot = MarioneBot(build_services(config, pool), VoicePlayer(lambda: None))
    try:
        for extension in EXTENSIONS:
            await bot.load_extension(extension)
        assert {"EconomyCog", "EntranceCog", "RolesCog", "AgentCog", "CommandsCog"} <= set(bot.cogs)
        names = {c.name for c in bot.tree.get_commands()}
        assert {"marione", "marione-admin"} <= names
        marione = next(c for c in bot.tree.get_commands() if c.name == "marione")
        assert isinstance(marione, discord.app_commands.Group)
        assert {
            "balance",
            "pay",
            "rob",
            "leaderboard",
            "history",
            "soundboard",
            "soundboard-add",
            "language",
            "forget",
        } <= {c.name for c in marione.commands}
    finally:
        for name in list(bot.cogs):
            await bot.remove_cog(name)
        await bot.close()


def test_trigger_regex_compiles_for_the_names_the_cog_uses() -> None:
    from marione.bot.cogs.agent import TRIGGER_WORDS

    patterns = [compile_trigger(w) for w in TRIGGER_WORDS]
    assert all(isinstance(p, re.Pattern) for p in patterns)
