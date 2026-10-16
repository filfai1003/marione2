"""The hard, code-enforced limits on the AI's economic actions (gift and fine).

The model is told when to act, but these rules decide whether the action really happens. The
database repeats the most important one (no AI entry above 500) as a constraint.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from marione.domain.rules import AgentRules


class ActionKind(StrEnum):
    GIFT = "gift"
    FINE = "fine"


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    amount: int
    reason: str = ""


def check_agent_action(
    *,
    amount: int,
    target_id: int,
    bot_id: int,
    now: datetime,
    last_action_at: datetime | None,
    rules: AgentRules,
) -> ActionDecision:
    """May the AI move `amount` coins to or from `target_id` right now?"""
    if amount <= 0:
        return ActionDecision(False, 0, "the amount must be positive")
    if target_id == bot_id:
        return ActionDecision(False, 0, "the bot cannot act on its own balance")
    if last_action_at is not None:
        elapsed = (now - last_action_at).total_seconds()
        if elapsed < rules.user_cooldown_seconds:
            return ActionDecision(False, 0, "this member was acted on a moment ago")
    return ActionDecision(True, min(amount, rules.max_amount))
