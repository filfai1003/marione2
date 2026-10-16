"""Wealth tiers: the server role a member earns from their balance."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    key: str
    name: str
    min_balance: int
    color: int  # 0xRRGGBB
    emoji: str

    @property
    def hex(self) -> str:
        return f"#{self.color:06X}"


TIERS: tuple[Tier, ...] = (
    Tier("morto-di-fame", "Morto di fame", 0, 0x95A5A6, "🥀"),
    Tier("racimola-spiccioli", "Racimola-spiccioli", 100, 0x3498DB, "🪙"),
    Tier("sbarca-il-lunario", "Sbarca il lunario", 1_000, 0x1ABC9C, "🧑‍🍳"),
    Tier("portafoglio-gonfio", "Portafoglio gonfio", 10_000, 0x2ECC71, "👛"),
    Tier("ricco-del-quartiere", "Ricco del quartiere", 100_000, 0xF1C40F, "🏘️"),
    Tier("sceicco-del-divano", "Sceicco del divano", 1_000_000, 0xE67E22, "🛋️"),
    Tier("nababbo-in-ciabatte", "Nababbo in ciabatte", 10_000_000, 0xE74C3C, "🩴"),
    Tier("magnate-degli-spaghetti", "Magnate degli spaghetti", 100_000_000, 0xE91E63, "🍝"),
    Tier("re-della-pastasciutta", "Re della pastasciutta", 1_000_000_000, 0x9B59B6, "👑"),
    Tier("faraone-del-ragu", "Faraone del ragù", 10_000_000_000, 0x8E44AD, "🏺"),
    Tier("imperatore-della-poltrona", "Imperatore della poltrona", 100_000_000_000, 0x34495E, "🪑"),
    Tier("divinita-spaghettara", "Divinità Spaghettara", 1_000_000_000_000, 0xFFD700, "🔱"),
)


def tier_for(balance: int) -> Tier:
    """The highest tier whose threshold the balance reaches."""
    best = TIERS[0]
    for tier in TIERS:
        if balance >= tier.min_balance:
            best = tier
    return best


def next_tier(balance: int) -> Tier | None:
    for tier in TIERS:
        if tier.min_balance > balance:
            return tier
    return None


@dataclass(frozen=True)
class RoleChange:
    user_id: int
    add: str | None  # tier key to give (None = already has it)
    remove: tuple[str, ...]  # tier keys to take away


def plan_changes(
    balances: dict[int, int], held: dict[int, set[str]], *, min_balance: int = 1
) -> list[RoleChange]:
    """What to change so each member holds exactly the role of their tier.

    `held` maps a member to the tier keys they currently hold (only Marione's own roles).
    Members below `min_balance` are left alone unless they hold a stale tier role.
    """
    changes: list[RoleChange] = []
    for user_id in sorted(set(balances) | set(held)):
        mine = held.get(user_id, set())
        balance = balances.get(user_id, 0)
        wanted = tier_for(balance).key if balance >= min_balance else None
        remove = tuple(sorted(k for k in mine if k != wanted))
        add = wanted if wanted is not None and wanted not in mine else None
        if add or remove:
            changes.append(RoleChange(user_id, add, remove))
    return changes
