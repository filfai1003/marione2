"""Slash commands: /marione (everyone) and /marione-admin (administrators).

Names and descriptions are English, localised to Italian and French by Discord (see
`bot/commands_i18n.py`); answers use the member's language (their choice, else their Discord app
language, else the server's). Public lines use the server's language.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.app_commands import locale_str as _

from marione.bot.texts import pay_line, rob_line, rob_refusal
from marione.bot.voice import PlayStatus
from marione.db.settings import FEATURES
from marione.db.sounds import SoundError
from marione.domain.roles import tier_for
from marione.i18n import LANGS, t, unit
from marione.labels import describe
from marione.llm.budget import period_starts
from marione.media.ytdl import MusicError

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

from discord.ext import commands

logger = logging.getLogger("marione.commands")

LANGUAGE_CHOICES = [
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Italiano", value="it"),
    app_commands.Choice(name="Français", value="fr"),
]


class CommandsCog(commands.Cog):
    marione = app_commands.Group(
        name="marione", description=_("Marioncelli, sounds and more"), guild_only=True
    )
    admin = app_commands.Group(
        name="marione-admin",
        description=_("Tools for administrators"),
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot

    async def lang(self, interaction: discord.Interaction) -> str:
        return await self.bot.services.settings.language_for(
            interaction.user.id, str(interaction.locale)
        )

    async def server_lang(self) -> str:
        return await self.bot.services.settings.server_language()

    @staticmethod
    def is_admin(interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        return bool(perms and perms.administrator)

    # --- everyone ------------------------------------------------------------------------------

    @marione.command(
        name=_("balance"), description=_("How many Marioncelli you (or another member) have")
    )
    @app_commands.rename(member=_("member"))
    async def balance(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        lang = await self.lang(interaction)
        target = member or interaction.user
        ledger = self.bot.services.ledger
        amount = await ledger.balance(target.id)
        tier = tier_for(amount)
        rank, total = await ledger.rank_of(target.id)
        place = t("rank_place", lang, rank=rank, total=total) if rank else ""
        line = t("balance_line", lang, name=target.display_name, amount=amount, unit=unit(amount))
        await interaction.response.send_message(
            f"{line}\n{tier.emoji} {tier.name}{place}", ephemeral=member is None
        )

    @marione.command(name=_("pay"), description=_("Give Marioncelli to another member"))
    @app_commands.rename(member=_("member"), amount=_("amount"))
    async def pay(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        lang = await self.lang(interaction)
        if member.bot or member.id == interaction.user.id:
            await interaction.response.send_message(t("pay_self_or_bot", lang), ephemeral=True)
            return
        svc = self.bot.services
        if not await svc.settings.is_enabled("economy"):
            await interaction.response.send_message(t("economy_paused", lang), ephemeral=True)
            return
        await svc.ledger.remember_name(interaction.user.id, interaction.user.display_name)
        await svc.ledger.remember_name(member.id, member.display_name)
        # The interaction id makes a double click or a retry pay only once.
        ok = await svc.economy.pay(
            interaction.user.id, member.id, amount, key=f"pay:{interaction.id}"
        )
        if not ok:
            await interaction.response.send_message(t("not_enough", lang), ephemeral=True)
            return
        await interaction.response.send_message(
            pay_line(
                interaction.user.display_name, member.display_name, amount, await self.server_lang()
            )
        )

    @marione.command(name=_("rob"), description=_("Try a heist: if you get caught you pay a fine"))
    @app_commands.rename(member=_("member"), amount=_("amount"))
    async def rob(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000_000],
    ) -> None:
        lang = await self.lang(interaction)
        svc = self.bot.services
        if member.bot or not (
            await svc.settings.is_enabled("economy") and await svc.settings.is_enabled("rob")
        ):
            await interaction.response.send_message(t("rob_unavailable", lang), ephemeral=True)
            return
        await svc.ledger.remember_name(interaction.user.id, interaction.user.display_name)
        await svc.ledger.remember_name(member.id, member.display_name)
        result = await svc.economy.rob(interaction.user.id, member.id, amount)
        if result.refused:
            await interaction.response.send_message(
                rob_refusal(result, svc.economy_rules.robbery.min_amount, lang), ephemeral=True
            )
            return
        await interaction.response.send_message(
            rob_line(
                interaction.user.display_name, member.display_name, result, await self.server_lang()
            )
        )

    @marione.command(name=_("leaderboard"), description=_("The richest members"))
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        top = await self.bot.services.ledger.top(10)
        if not top:
            await interaction.response.send_message(t("nobody_rich", lang), ephemeral=True)
            return
        lines = [
            f"**{i}.** {name or uid} — {bal}" for i, (uid, name, bal) in enumerate(top, start=1)
        ]
        await interaction.response.send_message(
            t("leaderboard_title", lang) + "\n" + "\n".join(lines)
        )

    @marione.command(name=_("history"), description=_("Your latest transactions"))
    async def history(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        ledger = self.bot.services.ledger
        entries = await ledger.history(interaction.user.id, 10)
        if not entries:
            await interaction.response.send_message(t("no_moves", lang), ephemeral=True)
            return
        lines = []
        for e in entries:
            other = await ledger.name_of(e.counterparty, "") if e.counterparty else None
            lines.append(f"`#{e.id}` {e.delta:+d} — {describe(e.reason, other, lang)}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @marione.command(
        name="soundboard", description=_("Play a soundboard sound in your voice channel")
    )
    @app_commands.rename(sound=_("sound"))
    async def board_play(self, interaction: discord.Interaction, sound: str) -> None:
        lang = await self.lang(interaction)
        svc = self.bot.services
        voice = getattr(interaction.user, "voice", None)
        if voice is None or voice.channel is None:
            await interaction.response.send_message(t("not_in_voice", lang), ephemeral=True)
            return
        if not await svc.settings.is_enabled("soundboard"):
            await interaction.response.send_message(t("soundboard_paused", lang), ephemeral=True)
            return
        found = await svc.soundboard.search(sound, 1)
        audio = await svc.soundboard.audio(found[0].id) if found else None
        if audio is None:
            await interaction.response.send_message(t("sound_not_found", lang), ephemeral=True)
            return
        volume = await svc.settings.soundboard_volume() / 100
        status = await self.bot.voice.play(voice.channel, audio.data, volume=volume)
        ok = status is PlayStatus.OK
        message = f"{found[0].emoji} **{audio.name}**" if ok else t("play_error", lang)
        await interaction.response.send_message(message, ephemeral=not ok)

    @board_play.autocomplete("sound")
    async def _board_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        sounds = await self.bot.services.soundboard.search(current, 25)
        return [app_commands.Choice(name=f"{s.emoji} {s.name}"[:100], value=s.name) for s in sounds]

    @marione.command(name=_("soundboard-add"), description=_("Add a sound to the soundboard"))
    @app_commands.rename(file=_("file"), name=_("name"), emoji=_("emoji"))
    async def board_add(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        name: str | None = None,
        emoji: str | None = None,
    ) -> None:
        lang = await self.lang(interaction)
        await interaction.response.defer(ephemeral=True)
        title = (name or file.filename.rsplit(".", 1)[0]).strip()
        try:
            await self.bot.services.sound_service.add_to_board(
                interaction.user.id, title, emoji or "🔊", await file.read()
            )
        except SoundError:
            await interaction.followup.send(f"❌ {t('invalid_audio', lang)}", ephemeral=True)
            return
        await interaction.followup.send(t("board_added", lang, name=title), ephemeral=True)

    # --- music -------------------------------------------------------------------------------

    @marione.command(name=_("play"), description=_("Play a song from a link or a title"))
    @app_commands.rename(query=_("query"))
    async def music_play(self, interaction: discord.Interaction, query: str) -> None:
        lang = await self.lang(interaction)
        svc = self.bot.services
        player = self.bot.music
        voice = getattr(interaction.user, "voice", None)
        if player is None or not await svc.settings.is_enabled("music"):
            await interaction.response.send_message(t("feature_off", lang), ephemeral=True)
            return
        if voice is None or voice.channel is None:
            await interaction.response.send_message(t("not_in_voice", lang), ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            track = await svc.ytdl.resolve(query)  # a title: the most likely result
        except MusicError:
            await interaction.followup.send(t("music_not_found", lang))
            return
        status, position = await player.request(
            track, interaction.user.id, interaction.user.display_name, voice.channel
        )
        keys = {
            "playing": "music_playing",
            "queued": "music_queued",
            "busy": "music_busy",
            "queue_full": "music_queue_full",
            "not_in_voice": "not_in_voice",
        }
        await interaction.followup.send(
            t(keys.get(status, "music_error"), lang, title=track.title, position=position)
            + (f"\n<{track.url}>" if status in ("playing", "queued") else "")
        )

    @marione.command(name=_("skip"), description=_("Skip to the next song"))
    async def music_skip(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        player = self.bot.music
        if player is None or await player.skip() == "nothing":
            await interaction.response.send_message(t("music_nothing", lang), ephemeral=True)
            return
        await interaction.response.send_message(t("music_skipped", lang))

    @marione.command(name=_("stop"), description=_("Stop the music and clear the queue"))
    async def music_stop(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        if self.bot.music is not None:
            self.bot.music.stop()
        await interaction.response.send_message(t("music_stopped", lang))

    @marione.command(name=_("pause"), description=_("Pause or resume the music"))
    async def music_pause(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        player = self.bot.music
        if player is None or player.queue.current is None:
            await interaction.response.send_message(t("music_nothing", lang), ephemeral=True)
            return
        paused = player.toggle_pause()
        await interaction.response.send_message(
            t("music_paused" if paused else "music_resumed", lang)
        )

    @marione.command(name=_("queue"), description=_("What is playing and what comes next"))
    async def music_queue(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        player = self.bot.music
        current = player.queue.current if player else None
        if player is None or current is None:
            await interaction.response.send_message(t("music_nothing", lang), ephemeral=True)
            return
        lines = [
            t("music_queue_title", lang),
            f"▶️ **{current.track.title}** · {current.requester_name}",
        ]
        lines += [
            f"`{i}.` {e.track.title} · {e.requester_name}"
            for i, e in enumerate(player.queue.upcoming[:10], start=1)
        ]
        if not player.queue.upcoming:
            lines.append(t("music_next_empty", lang))
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @marione.command(name=_("language"), description=_("The language Marione uses with you"))
    @app_commands.rename(language=_("language"))
    @app_commands.choices(language=LANGUAGE_CHOICES)
    async def language(
        self, interaction: discord.Interaction, language: app_commands.Choice[str]
    ) -> None:
        code = await self.bot.services.settings.set_user_language(
            interaction.user.id, language.value
        )
        await interaction.response.send_message(t("lang_set", code), ephemeral=True)

    @marione.command(
        name=_("forget"), description=_("Erase everything Marione remembers about you")
    )
    async def forget(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        agent = self.bot.chat_agent
        svc = self.bot.services
        count = (
            await agent.forget(interaction.user.id)
            if agent is not None
            else await svc.memory.forget_member(interaction.user.id)
        )
        count += await svc.chatlog.forget_member(interaction.user.id)
        count += await svc.music.forget_member(interaction.user.id)
        if agent is None:
            count += await svc.habits.forget_member(interaction.user.id)
        await interaction.response.send_message(t("forgot", lang, count=count), ephemeral=True)

    # --- administrators ------------------------------------------------------------------------

    @admin.command(name=_("give"), description=_("Give Marioncelli to a member"))
    @app_commands.rename(member=_("member"), amount=_("amount"))
    async def admin_gift(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        ledger = self.bot.services.ledger
        await ledger.remember_name(member.id, member.display_name)
        current = await ledger.balance(member.id)
        await ledger.set_balance(member.id, current + amount, admin_id=interaction.user.id)
        await interaction.response.send_message(
            t("admin_gift", await self.lang(interaction), amount=amount, name=member.display_name),
            ephemeral=True,
        )

    @admin.command(name=_("fine"), description=_("Take Marioncelli from a member"))
    @app_commands.rename(member=_("member"), amount=_("amount"))
    async def admin_fine(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        ledger = self.bot.services.ledger
        await ledger.remember_name(member.id, member.display_name)
        current = await ledger.balance(member.id)
        await ledger.set_balance(member.id, max(0, current - amount), admin_id=interaction.user.id)
        await interaction.response.send_message(
            t("admin_fine", await self.lang(interaction), amount=amount, name=member.display_name),
            ephemeral=True,
        )

    @admin.command(name=_("set"), description=_("Set a member's balance"))
    @app_commands.rename(member=_("member"), amount=_("amount"))
    async def admin_set(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 0, 10_000_000_000],
    ) -> None:
        ledger = self.bot.services.ledger
        await ledger.remember_name(member.id, member.display_name)
        await ledger.set_balance(member.id, amount, admin_id=interaction.user.id)
        await interaction.response.send_message(
            t("admin_set", await self.lang(interaction), amount=amount, name=member.display_name),
            ephemeral=True,
        )

    @admin.command(
        name=_("undo"),
        description=_("Undo an operation by its entry number (see /marione history)"),
    )
    @app_commands.rename(entry=_("entry"))
    async def admin_undo(self, interaction: discord.Interaction, entry: int) -> None:
        lang = await self.lang(interaction)
        ledger = self.bot.services.ledger
        group = await ledger.group_of(entry)
        if group is None:
            await interaction.response.send_message(t("move_not_found", lang), ephemeral=True)
            return
        count = await ledger.reverse(group)
        await interaction.response.send_message(
            t("undone", lang, count=count) if count else t("already_undone", lang), ephemeral=True
        )

    @admin.command(name=_("feature"), description=_("Switch a feature on or off"))
    @app_commands.rename(name=_("name"), enabled=_("enabled"))
    @app_commands.choices(name=[app_commands.Choice(name=f, value=f) for f in FEATURES])
    async def admin_feature(
        self, interaction: discord.Interaction, name: app_commands.Choice[str], enabled: bool
    ) -> None:
        lang = await self.lang(interaction)
        await self.bot.services.settings.set_enabled(name.value, enabled)
        await interaction.response.send_message(
            t(
                "feature_set",
                lang,
                icon="✅" if enabled else "⛔",
                name=name.value,
                state=t("on" if enabled else "off", lang),
            ),
            ephemeral=True,
        )

    @admin.command(
        name=_("server-language"),
        description=_("Language of Marione's public messages in this server"),
    )
    @app_commands.rename(language=_("language"))
    @app_commands.choices(language=LANGUAGE_CHOICES)
    async def admin_server_language(
        self, interaction: discord.Interaction, language: app_commands.Choice[str]
    ) -> None:
        code = await self.bot.services.settings.set_server_language(language.value)
        await interaction.response.send_message(t("lang_set", code), ephemeral=True)

    @admin.command(name=_("entrance-add"), description=_("Add an entrance sound for a member"))
    @app_commands.rename(member=_("member"), file=_("file"), name=_("name"))
    async def entrance_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        file: discord.Attachment,
        name: str | None = None,
    ) -> None:
        lang = await self.lang(interaction)
        await interaction.response.defer(ephemeral=True)
        title = (name or file.filename.rsplit(".", 1)[0]).strip()
        svc = self.bot.services
        await svc.ledger.remember_name(member.id, member.display_name)
        try:
            await svc.sound_service.add_entrance(member.id, title, await file.read())
        except SoundError as exc:
            key = "sound_exists" if "already" in str(exc) else "invalid_audio"
            await interaction.followup.send(f"❌ {t(key, lang)}", ephemeral=True)
            return
        await interaction.followup.send(
            t("entrance_saved", lang, name=title, member=member.display_name), ephemeral=True
        )

    @admin.command(name=_("entrance-list"), description=_("A member's entrance sounds"))
    @app_commands.rename(member=_("member"))
    async def entrance_list(self, interaction: discord.Interaction, member: discord.Member) -> None:
        lang = await self.lang(interaction)
        sounds = await self.bot.services.sounds.list(member.id)
        text = "\n".join(f"• {s.name} ({s.size // 1024} KB)" for s in sounds) or t(
            "entrance_none", lang, member=member.display_name
        )
        await interaction.response.send_message(text, ephemeral=True)

    @admin.command(name=_("entrance-remove"), description=_("Delete an entrance sound of a member"))
    @app_commands.rename(member=_("member"), name=_("name"))
    async def entrance_remove(
        self, interaction: discord.Interaction, member: discord.Member, name: str
    ) -> None:
        lang = await self.lang(interaction)
        removed = await self.bot.services.sounds.remove(member.id, name.strip())
        await interaction.response.send_message(
            t("deleted", lang) if removed else t("sound_not_found", lang), ephemeral=True
        )

    @admin.command(name=_("soundboard-remove"), description=_("Delete a sound from the soundboard"))
    @app_commands.rename(sound=_("sound"))
    async def board_remove(self, interaction: discord.Interaction, sound: str) -> None:
        lang = await self.lang(interaction)
        svc = self.bot.services
        found = await svc.soundboard.search(sound, 1)
        if not found or not self.is_admin(interaction):
            await interaction.response.send_message(t("sound_not_found", lang), ephemeral=True)
            return
        await svc.soundboard.remove(found[0].id)
        await interaction.response.send_message(t("deleted", lang), ephemeral=True)

    @board_remove.autocomplete("sound")
    async def _board_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        sounds = await self.bot.services.soundboard.search(current, 25)
        return [app_commands.Choice(name=f"{s.emoji} {s.name}"[:100], value=s.name) for s in sounds]

    @admin.command(
        name=_("import-old"),
        description=_("Import balances, soundboard and entrance sounds from the old Marione"),
    )
    async def admin_legacy(self, interaction: discord.Interaction) -> None:
        lang = await self.lang(interaction)
        cog = self.bot.get_cog("LegacyCog")
        await interaction.response.defer(ephemeral=True, thinking=True)
        report = await cog.run() if cog is not None else None  # type: ignore[attr-defined]
        if report is None:
            await interaction.followup.send(t("legacy_missing", lang), ephemeral=True)
            return
        lines = [t("legacy_done", lang, summary=report.summary())]
        lines += [f"• {s}" for s in report.skipped[:10]]
        await interaction.followup.send("\n".join(lines)[:1900], ephemeral=True)

    @admin.command(name=_("status"), description=_("Features, AI costs, balance check"))
    async def admin_status(self, interaction: discord.Interaction) -> None:
        svc = self.bot.services
        flags = await svc.settings.flags()
        day, month = period_starts(datetime.now(UTC), ZoneInfo(svc.config.timezone))
        main, gate = await svc.settings.ai_models()
        lines = [
            "**Features**: " + ", ".join(f"{k} {'✅' if v else '⛔'}" for k, v in flags.items()),
            f"**Languages**: {', '.join(LANGS)} · server: {await svc.settings.server_language()}",
        ]
        if svc.llm is None:
            lines.append("**AI**: off (OPENROUTER_API_KEY missing)")
        else:
            spent_day = await svc.usage.spent_since(day)
            spent_month = await svc.usage.spent_since(month)
            lines.append(
                f"**AI** {main or svc.config.agent_model} / {gate or svc.config.agent_gate_model}"
                f" · today ${spent_day:.4f} / ${svc.config.agent_daily_budget_usd} · "
                f"month ${spent_month:.4f} / ${svc.config.agent_monthly_budget_usd}"
            )
            by_model = await svc.usage.by_model_since(datetime.now(UTC) - timedelta(days=7))
            lines += [f"  · {m}: {n} calls, ${c:.4f} (7 days)" for m, n, c in by_model[:5]]
        wrong = await svc.ledger.audit()
        lines.append("**Balances**: " + ("consistent ✅" if not wrong else f"⚠️ {wrong}"))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(CommandsCog(bot))
