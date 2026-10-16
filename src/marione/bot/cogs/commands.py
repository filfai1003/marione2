"""Slash commands: /marione (everyone) and /marione-admin (administrators)."""

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from marione.bot.adapters import unit
from marione.bot.texts import pay_line, rob_line, rob_refusal
from marione.bot.voice import PlayStatus
from marione.db.settings import FEATURES
from marione.db.sounds import SoundError
from marione.domain.roles import tier_for
from marione.labels import describe

if TYPE_CHECKING:
    from marione.bot.app import MarioneBot

logger = logging.getLogger("marione.commands")


class CommandsCog(commands.Cog):
    marione = app_commands.Group(
        name="marione", description="Marioncelli, suoni e altro", guild_only=True
    )
    admin = app_commands.Group(
        name="marione-admin",
        description="Strumenti per gli amministratori",
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: "MarioneBot") -> None:
        self.bot = bot

    # --- everyone ------------------------------------------------------------------------------

    @marione.command(name="saldo", description="Quanti Marioncelli hai (o ha un altro membro)")
    async def balance(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ) -> None:
        target = membro or interaction.user
        ledger = self.bot.services.ledger
        amount = await ledger.balance(target.id)
        tier = tier_for(amount)
        rank, total = await ledger.rank_of(target.id)
        place = f" · #{rank} su {total}" if rank else ""
        await interaction.response.send_message(
            f"💰 **{target.display_name}** ha **{amount} {unit(amount)}**\n"
            f"{tier.emoji} {tier.name}{place}",
            ephemeral=membro is None,
        )

    @marione.command(name="paga", description="Dai dei Marioncelli a un altro membro")
    async def pay(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        importo: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        if membro.bot or membro.id == interaction.user.id:
            await interaction.response.send_message(
                "Non puoi pagare te stesso o un bot.", ephemeral=True
            )
            return
        svc = self.bot.services
        if not await svc.settings.is_enabled("economy"):
            await interaction.response.send_message("L'economia è in pausa.", ephemeral=True)
            return
        await svc.ledger.remember_name(interaction.user.id, interaction.user.display_name)
        await svc.ledger.remember_name(membro.id, membro.display_name)
        # The interaction id makes a double click or a retry pay only once.
        ok = await svc.economy.pay(
            interaction.user.id, membro.id, importo, key=f"pay:{interaction.id}"
        )
        if not ok:
            await interaction.response.send_message(
                "Non hai abbastanza Marioncelli.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            pay_line(interaction.user.display_name, membro.display_name, importo)
        )

    @marione.command(name="deruba", description="Tenta un furto: se ti beccano paghi una multa")
    async def rob(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        importo: app_commands.Range[int, 1, 1_000_000_000],
    ) -> None:
        svc = self.bot.services
        if membro.bot or not (
            await svc.settings.is_enabled("economy") and await svc.settings.is_enabled("rob")
        ):
            await interaction.response.send_message(
                "Il furto non è disponibile adesso.", ephemeral=True
            )
            return
        await svc.ledger.remember_name(interaction.user.id, interaction.user.display_name)
        await svc.ledger.remember_name(membro.id, membro.display_name)
        result = await svc.economy.rob(interaction.user.id, membro.id, importo)
        if result.refused:
            await interaction.response.send_message(
                rob_refusal(result, svc.economy_rules.robbery.min_amount), ephemeral=True
            )
            return
        await interaction.response.send_message(
            rob_line(interaction.user.display_name, membro.display_name, result)
        )

    @marione.command(name="classifica", description="I più ricchi del server")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        top = await self.bot.services.ledger.top(10)
        if not top:
            await interaction.response.send_message(
                "Nessuno ha ancora un Marioncello.", ephemeral=True
            )
            return
        lines = [
            f"**{i}.** {name or uid} — {bal}" for i, (uid, name, bal) in enumerate(top, start=1)
        ]
        await interaction.response.send_message("🏆 **Classifica**\n" + "\n".join(lines))

    @marione.command(name="storico", description="I tuoi ultimi movimenti")
    async def history(self, interaction: discord.Interaction) -> None:
        entries = await self.bot.services.ledger.history(interaction.user.id, 10)
        if not entries:
            await interaction.response.send_message("Nessun movimento.", ephemeral=True)
            return
        lines = [f"`#{e.id}` {e.delta:+d} — {describe(e.reason)}" for e in entries]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @marione.command(
        name="suono-aggiungi", description="Aggiungi un audio che suona quando entri in vocale"
    )
    async def sound_add(
        self, interaction: discord.Interaction, file: discord.Attachment, nome: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        name = (nome or file.filename.rsplit(".", 1)[0]).strip()
        try:
            await self.bot.services.sound_service.add_entrance(
                interaction.user.id, name, await file.read()
            )
        except SoundError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return
        await interaction.followup.send(f"🔊 Salvato **{name}**.", ephemeral=True)

    @marione.command(name="suono-lista", description="I tuoi audio")
    async def sound_list(self, interaction: discord.Interaction) -> None:
        sounds = await self.bot.services.sounds.list(interaction.user.id)
        text = "\n".join(f"• {s.name} ({s.size // 1024} KB)" for s in sounds) or "Non hai audio."
        await interaction.response.send_message(text, ephemeral=True)

    @marione.command(name="suono-rimuovi", description="Elimina uno dei tuoi audio")
    async def sound_remove(self, interaction: discord.Interaction, nome: str) -> None:
        removed = await self.bot.services.sounds.remove(interaction.user.id, nome.strip())
        await interaction.response.send_message(
            "🗑️ Eliminato." if removed else "Non ho trovato questo audio.", ephemeral=True
        )

    @marione.command(name="soundboard", description="Suona un suono della soundboard in vocale")
    @app_commands.describe(suono="Il suono da suonare")
    async def board_play(self, interaction: discord.Interaction, suono: str) -> None:
        svc = self.bot.services
        voice = getattr(interaction.user, "voice", None)
        if voice is None or voice.channel is None:
            await interaction.response.send_message(
                "Entra prima in un canale vocale 🎧", ephemeral=True
            )
            return
        if not await svc.settings.is_enabled("soundboard"):
            await interaction.response.send_message("La soundboard è in pausa.", ephemeral=True)
            return
        found = await svc.soundboard.search(suono, 1)
        audio = await svc.soundboard.audio(found[0].id) if found else None
        if audio is None:
            await interaction.response.send_message("Non trovo questo suono.", ephemeral=True)
            return
        volume = await svc.settings.soundboard_volume() / 100
        status = await self.bot.voice.play(voice.channel, audio.data, volume=volume, interrupt=True)
        message = (
            f"{found[0].emoji} **{audio.name}**"
            if status is PlayStatus.OK
            else "Non riesco a suonare adesso, riprova."
        )
        await interaction.response.send_message(message, ephemeral=status is not PlayStatus.OK)

    @board_play.autocomplete("suono")
    async def _board_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        sounds = await self.bot.services.soundboard.search(current, 25)
        return [app_commands.Choice(name=f"{s.emoji} {s.name}"[:100], value=s.name) for s in sounds]

    @marione.command(name="soundboard-aggiungi", description="Aggiungi un suono alla soundboard")
    async def board_add(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        nome: str | None = None,
        emoji: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        name = (nome or file.filename.rsplit(".", 1)[0]).strip()
        try:
            await self.bot.services.sound_service.add_to_board(
                interaction.user.id, name, emoji or "🔊", await file.read()
            )
        except SoundError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return
        await interaction.followup.send(f"🔊 **{name}** è nella soundboard.", ephemeral=True)

    @marione.command(name="soundboard-rimuovi", description="Elimina un tuo suono dalla soundboard")
    @app_commands.describe(suono="Il suono da eliminare")
    async def board_remove(self, interaction: discord.Interaction, suono: str) -> None:
        svc = self.bot.services
        found = await svc.soundboard.search(suono, 1)
        sound = found[0] if found else None
        is_admin = bool(getattr(interaction.user, "guild_permissions", None)) and bool(
            interaction.user.guild_permissions.administrator  # type: ignore[union-attr]
        )
        if sound is None or not svc.sound_service.may_modify(
            sound, interaction.user.id, is_admin=is_admin
        ):
            await interaction.response.send_message(
                "Non trovo un suono tuo con questo nome.", ephemeral=True
            )
            return
        await svc.soundboard.remove(sound.id)
        await interaction.response.send_message("🗑️ Eliminato.", ephemeral=True)

    @board_remove.autocomplete("suono")
    async def _board_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        sounds = await self.bot.services.soundboard.search(current, 25)
        return [app_commands.Choice(name=f"{s.emoji} {s.name}"[:100], value=s.name) for s in sounds]

    @marione.command(
        name="dimentica", description="Cancella tutto quello che Marione ricorda di te"
    )
    async def forget(self, interaction: discord.Interaction) -> None:
        agent = self.bot.chat_agent
        svc = self.bot.services
        count = (
            await agent.forget(interaction.user.id)
            if agent is not None
            else await svc.memory.forget_member(interaction.user.id)
        )
        count += await svc.chatlog.forget_member(interaction.user.id)
        await interaction.response.send_message(
            f"🧽 Fatto: ho dimenticato {count} cose su di te.", ephemeral=True
        )

    # --- administrators ------------------------------------------------------------------------

    @admin.command(name="regala", description="Dai Marioncelli a un membro")
    async def admin_gift(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        importo: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        ledger = self.bot.services.ledger
        await ledger.remember_name(membro.id, membro.display_name)
        current = await ledger.balance(membro.id)
        await ledger.set_balance(membro.id, current + importo, admin_id=interaction.user.id)
        await interaction.response.send_message(
            f"🎁 +{importo} a **{membro.display_name}**", ephemeral=True
        )

    @admin.command(name="multa", description="Togli Marioncelli a un membro")
    async def admin_fine(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        importo: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        ledger = self.bot.services.ledger
        await ledger.remember_name(membro.id, membro.display_name)
        current = await ledger.balance(membro.id)
        await ledger.set_balance(membro.id, max(0, current - importo), admin_id=interaction.user.id)
        await interaction.response.send_message(
            f"⚖️ -{importo} a **{membro.display_name}**", ephemeral=True
        )

    @admin.command(name="imposta", description="Imposta il saldo di un membro")
    async def admin_set(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        saldo: app_commands.Range[int, 0, 10_000_000_000],
    ) -> None:
        ledger = self.bot.services.ledger
        await ledger.remember_name(membro.id, membro.display_name)
        await ledger.set_balance(membro.id, saldo, admin_id=interaction.user.id)
        await interaction.response.send_message(
            f"✏️ **{membro.display_name}** ora ha {saldo}", ephemeral=True
        )

    @admin.command(
        name="annulla",
        description="Annulla un'operazione dal numero del movimento (vedi /marione storico)",
    )
    async def admin_undo(self, interaction: discord.Interaction, movimento: int) -> None:
        ledger = self.bot.services.ledger
        group = await ledger.group_of(movimento)
        if group is None:
            await interaction.response.send_message("Movimento non trovato.", ephemeral=True)
            return
        count = await ledger.reverse(group)
        await interaction.response.send_message(
            f"↩️ Annullati {count} movimenti." if count else "Era già stato annullato.",
            ephemeral=True,
        )

    @admin.command(name="funzione", description="Attiva o disattiva una funzione")
    @app_commands.choices(nome=[app_commands.Choice(name=f, value=f) for f in FEATURES])
    async def admin_feature(
        self, interaction: discord.Interaction, nome: app_commands.Choice[str], attiva: bool
    ) -> None:
        await self.bot.services.settings.set_enabled(nome.value, attiva)
        await interaction.response.send_message(
            f"{'✅' if attiva else '⛔'} **{nome.value}**: {'attiva' if attiva else 'spenta'}",
            ephemeral=True,
        )

    @admin.command(name="stato", description="Funzioni attive, costi dell'IA, controllo dei saldi")
    async def admin_status(self, interaction: discord.Interaction) -> None:
        from datetime import UTC, datetime, timedelta
        from zoneinfo import ZoneInfo

        from marione.llm.budget import period_starts

        svc = self.bot.services
        flags = await svc.settings.flags()
        day, month = period_starts(datetime.now(UTC), ZoneInfo(svc.config.timezone))
        lines = [
            "**Funzioni**: " + ", ".join(f"{k} {'✅' if v else '⛔'}" for k, v in flags.items())
        ]
        if svc.llm is None:
            lines.append("**IA**: spenta (manca OPENROUTER_API_KEY)")
        else:
            spent_day = await svc.usage.spent_since(day)
            spent_month = await svc.usage.spent_since(month)
            lines.append(
                f"**IA oggi** ${spent_day:.4f} / ${svc.config.agent_daily_budget_usd} · "
                f"**mese** ${spent_month:.4f} / ${svc.config.agent_monthly_budget_usd}"
            )
            by_model = await svc.usage.by_model_since(datetime.now(UTC) - timedelta(days=7))
            lines += [f"  · {m}: {n} chiamate, ${c:.4f} (7 giorni)" for m, n, c in by_model[:5]]
        wrong = await svc.ledger.audit()
        lines.append("**Saldi**: " + ("coerenti ✅" if not wrong else f"⚠️ incoerenti: {wrong}"))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: "MarioneBot") -> None:
    await bot.add_cog(CommandsCog(bot))
