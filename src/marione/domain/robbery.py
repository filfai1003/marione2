"""Robbery odds. Pure math, no I/O.

Design invariant: attempting a heist is ALWAYS a losing bet on average, for every amount and every
pair of balances: amount * P(success) < fine * P(failure). The success probability is a fraction of
the "breakeven ceiling" fine / (amount + fine), so the invariant follows from the shape of the
formula rather than from case-by-case checks (there is a property test for it).

Difficulty is made of two shares, not absolute amounts:
- audacity: the amount against the ATTACKER's wealth (a poor thief going big reaches far);
- victim impact: the amount against the VICTIM's wealth (a bite out of a poor victim is hard).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RobberyRules:
    min_amount: int = 1
    cooldown_seconds: int = 3600  # one attempt per attacker per hour
    p_max: float = 0.85  # the success chance never exceeds this
    difficulty_k: float = 6.0  # steepness of the difficulty curve
    victim_weight: float = 0.5  # weight of the victim-impact term
    fine_fraction: float = 0.5
    fine_base: float = 0.5
    fine_min: int = 1


@dataclass(frozen=True)
class Odds:
    probability: float
    fine: int  # what the attacker would pay on failure (already capped at their balance)


def fine_amount(amount: int, attacker: int, total: int, rules: RobberyRules) -> int:
    total = max(1, total)
    severity = rules.fine_base + total / (total + max(0, attacker) + 1)
    return max(rules.fine_min, round(rules.fine_fraction * max(0, amount) * severity))


def odds(amount: int, attacker: int, victim: int, total: int, rules: RobberyRules) -> Odds:
    attacker = max(0, attacker)
    amount = max(0, amount)
    fine = min(fine_amount(amount, attacker, total, rules), attacker)
    ceiling = fine / (amount + fine) if (amount + fine) > 0 else 0.0
    audacity = amount / max(1, attacker)
    impact = amount / max(1, victim)
    difficulty = audacity + rules.victim_weight * impact
    p = ceiling / (1 + rules.difficulty_k * difficulty)
    return Odds(min(rules.p_max, p), fine)
