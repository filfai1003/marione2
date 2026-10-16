"""Tunable numbers of the economy and of the AI's economic powers, in one place."""

from dataclasses import dataclass, field

from marione.domain.robbery import RobberyRules


@dataclass(frozen=True)
class EconomyRules:
    # Earning by chatting: one reward per substantial message, at most once per cooldown.
    message_reward: int = 1
    message_min_chars: int = 4
    message_cooldown_seconds: float = 20
    # Earning by being active in a voice channel.
    voice_per_minute: int = 2
    # Anti-spam: a flood or a repeat costs a percentage of the spammer's fortune.
    spam_window_seconds: float = 8
    spam_max_burst: int = 6
    spam_repeat: int = 3
    spam_penalty_pct: int = 10
    spam_penalty_min: int = 50
    spam_penalty_cooldown_seconds: float = 30
    robbery: RobberyRules = field(default_factory=RobberyRules)
    # Wealth roles are only given to members with at least this much.
    role_min_balance: int = 1


@dataclass(frozen=True)
class AgentRules:
    """Hard limits on what the AI may do with money. The model can never override them."""

    max_amount: int = 200  # per gift or fine (the database refuses more than 500 anyway)
    user_cooldown_seconds: float = 300  # between two AI actions on the same member
    max_tool_steps: int = 6  # model <-> tools round trips for one message
    max_tool_result_chars: int = 4000
