"""The public lines Marione says about money events: one place, used by Discord and the web."""

from marione.i18n import t, unit
from marione.services.economy import RobResult


def pay_line(sender: str, receiver: str, amount: int, lang: str | None = None) -> str:
    return t("pay_public", lang, sender=sender, receiver=receiver, amount=amount, unit=unit(amount))


def rob_line(attacker: str, victim: str, result: RobResult, lang: str | None = None) -> str:
    if result.status == "ok":
        return t(
            "rob_ok",
            lang,
            attacker=attacker,
            victim=victim,
            amount=result.amount,
            unit=unit(result.amount),
        )
    return t(
        "rob_caught",
        lang,
        attacker=attacker,
        victim=victim,
        fine=result.fine,
        unit=unit(result.fine),
    )


def rob_refusal(result: RobResult, min_amount: int, lang: str | None = None) -> str:
    keys = {
        "self": "rob_self",
        "too_small": "rob_too_small",
        "broke": "rob_broke",
        "victim_poor": "rob_victim_poor",
        "cooldown": "rob_cooldown",
    }
    return t(
        keys.get(result.status, "rob_unavailable"),
        lang,
        min=min_amount,
        unit=unit(min_amount),
        minutes=result.wait_seconds // 60 + 1,
    )
