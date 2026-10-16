"""The public lines Marione says about money events: one place, used by Discord and the web."""

from marione.bot.adapters import unit
from marione.services.economy import RobResult


def pay_line(sender: str, receiver: str, amount: int) -> str:
    return f"💸 **{sender}** ha dato **{amount} {unit(amount)}** a **{receiver}**"


def rob_line(attacker: str, victim: str, result: RobResult) -> str:
    if result.status == "ok":
        return (
            f"🥷 **{attacker}** ha svaligiato **{victim}** di "
            f"**{result.amount} {unit(result.amount)}**!"
        )
    return (
        f"🚨 **{attacker}** ci ha provato con **{victim}** ma l'hanno beccato: "
        f"multa di **{result.fine} {unit(result.fine)}** a favore di {victim}."
    )


def rob_refusal(result: RobResult, min_amount: int) -> str:
    wait_min = result.wait_seconds // 60 + 1
    return {
        "self": "Derubare te stesso? Marione è fiero della tua creatività, ma no.",
        "too_small": f"Un furto vale almeno {min_amount} {unit(min_amount)}.",
        "broke": "Sei al verde: senza Marioncelli non puoi rischiare un furto.",
        "victim_poor": "La vittima non ha abbastanza Marioncelli.",
        "cooldown": f"Ti stanno ancora cercando: riprova tra {wait_min} min.",
    }.get(result.status, "Furto non riuscito.")
