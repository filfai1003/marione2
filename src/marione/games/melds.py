"""Melds for the rummy family (scala 40, machiavelli), on French codes (see `cards.py`).

A meld is either

* a **set**: 3 or 4 cards of the same rank, all of different suits;
* a **run**: 3 or more consecutive cards of the same suit. The ace is low (A-2-3) or high
  (Q-K-A), never both: no wrap-around (K-A-2), so a run is at most 13 cards long.

Jokers ("X1".."X4") stand for any card, only where the caller allows them (scala 40). House rule:
**at most one joker per meld**, and a meld always holds at least two real cards. A joker that could
sit at either end of a run (5-6-X) is read as the higher card (7), which scores more.

Points (scala 40 opening): numbers at face value, T/J/Q/K 10, the ace 11 in a set or at the top of
a run (Q-K-A) and 1 at the bottom (A-2-3); a joker is worth the card it stands for.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

from marione.games.cards import FR_RANKS, FR_SUITS, is_joker

MAX_JOKERS = 1  # per meld (house rule)
JOKER_CODES = frozenset(f"X{i}" for i in range(1, 5))
# Run positions: 1 = low ace, 2..13 = 2..K, 14 = high ace.
_POS_RANK = {1: "A", **{i + 2: r for i, r in enumerate(FR_RANKS)}}

Kind = Literal["set", "run"]


@dataclass(frozen=True)
class Meld:
    kind: Kind
    cards: tuple[str, ...]  # display order (runs low to high, the joker in its place)
    stands: tuple[str, ...]  # what each card is: the joker replaced by the card it stands for
    positions: tuple[int, ...]  # runs: 1..14 per card; sets: the rank value per card

    @property
    def points(self) -> int:
        if self.kind == "set":
            return sum(_set_value(c) for c in self.stands)
        return sum(_run_value(p) for p in self.positions)


def _set_value(card: str) -> int:
    r = card[0]
    if r == "A":
        return 11
    if r in "TJQK":
        return 10
    return int(r)


def _run_value(pos: int) -> int:
    if pos == 1:
        return 1
    if pos == 14:
        return 11
    return min(pos, 10)


def card_points(card: str) -> int:
    """Penalty value of a card left in hand: joker 25, ace 11, T/J/Q/K 10, numbers face value."""
    if is_joker(card):
        return 25
    return _set_value(card)


def valid_card(card: object) -> bool:
    if not isinstance(card, str):
        return False
    if card in JOKER_CODES:
        return True
    return len(card) == 2 and card[0] in FR_RANKS and card[1] in FR_SUITS


def analyse(cards: Sequence[str], jokers: bool = True) -> Meld | None:
    """The meld these cards form (order does not matter), or None."""
    if len(cards) < 3 or not all(valid_card(c) for c in cards):
        return None
    wild = [c for c in cards if is_joker(c)]
    real = [c for c in cards if not is_joker(c)]
    if wild and not jokers:
        return None
    if len(wild) > MAX_JOKERS or len(real) < 2:
        return None
    return _as_set(real, wild) or _as_run(real, wild)


def is_meld(cards: Sequence[str], jokers: bool = True) -> bool:
    return analyse(cards, jokers) is not None


def meld_points(cards: Sequence[str], jokers: bool = True) -> int:
    meld = analyse(cards, jokers)
    if meld is None:
        raise ValueError(f"not a meld: {cards}")
    return meld.points


def _as_set(real: list[str], wild: list[str]) -> Meld | None:
    ranks = {c[0] for c in real}
    suits = [c[1] for c in real]
    if len(ranks) != 1 or len(set(suits)) != len(suits) or len(real) + len(wild) > 4:
        return None
    r = real[0][0]
    ordered = sorted(real, key=lambda c: FR_SUITS.index(c[1]))
    missing = [s for s in FR_SUITS if s not in suits]
    stands = ordered + [r + missing[i] for i in range(len(wild))]
    value = FR_RANKS.index(r) + 2
    return Meld("set", tuple(ordered + wild), tuple(stands), (value,) * len(stands))


def _as_run(real: list[str], wild: list[str]) -> Meld | None:
    suits = {c[1] for c in real}
    if len(suits) != 1 or len(real) + len(wild) > 13:
        return None
    s = real[0][1]
    ranks = [c[0] for c in real]
    if len(set(ranks)) != len(ranks):
        return None
    for ace in (1, 14) if "A" in ranks else (0,):
        pos = sorted(ace if r == "A" else FR_RANKS.index(r) + 2 for r in ranks)
        lo, hi = pos[0], pos[-1]
        gaps = [p for p in range(lo, hi + 1) if p not in pos]
        if len(gaps) > len(wild):
            continue
        extra = len(wild) - len(gaps)
        fill = list(gaps)
        if extra:
            if hi + extra <= 14 and not (ace == 1 and hi + extra == 14):
                fill += list(range(hi + 1, hi + extra + 1))
            elif lo - extra >= 1 and not (ace == 14 and lo - extra == 1):
                fill += list(range(lo - extra, lo))
            else:
                continue
        by_pos = dict(zip(pos, sorted(real, key=_run_key(ace)), strict=True))
        jokers = iter(wild)
        for p in fill:
            by_pos[p] = next(jokers)
        order = sorted(by_pos)
        return Meld(
            "run",
            tuple(by_pos[p] for p in order),
            tuple(_POS_RANK[p] + s for p in order),
            tuple(order),
        )
    return None


def _run_key(ace: int) -> Callable[[str], int]:
    def key(card: str) -> int:
        return ace if card[0] == "A" else FR_RANKS.index(card[0]) + 2

    return key


# --- finding melds in a hand ---------------------------------------------------------------------


def find_melds(hand: Iterable[str], jokers: bool = True) -> list[list[str]]:
    """Every candidate meld these cards can form on their own (duplicates collapsed; at most one
    joker each, the first joker of the hand). Overlapping candidates: pick with `best_partition`."""
    cards = list(hand)
    wild = sorted(c for c in cards if is_joker(c))
    joker = wild[0] if wild and jokers else None
    real = {c for c in cards if not is_joker(c)}
    found: list[list[str]] = []
    for r in FR_RANKS:
        present = [r + s for s in FR_SUITS if r + s in real]
        for size in (3, 4):
            found.extend(list(c) for c in combinations(present, size))
        if joker:
            for size in (2, 3):
                found.extend([*c, joker] for c in combinations(present, size))
    for s in FR_SUITS:
        have = {p for p in range(1, 15) if _POS_RANK[p] + s in real}
        for a in range(1, 13):
            for b in range(a + 2, min(a + 12, 14) + 1):
                window = range(a, b + 1)
                missing = [p for p in window if p not in have]
                if not missing:
                    found.append([_POS_RANK[p] + s for p in window])
                elif joker and len(missing) == 1:
                    found.append([_POS_RANK[p] + s for p in window if p in have] + [joker])
                elif len(missing) > 1:
                    break  # a wider window only has more gaps
    return [m for m in found if is_meld(m, jokers)]


def _norm(card: str) -> str:
    return "X" if is_joker(card) else card


def best_partition(
    hand: Sequence[str],
    candidates: Sequence[Sequence[str]],
    score: Callable[[Sequence[str]], int],
    keep: int = 0,
    required: str | None = None,
    node_cap: int = 4000,
) -> list[list[str]]:
    """Disjoint candidates (as a multiset of `hand`, jokers interchangeable) with the highest total
    `score`, leaving at least `keep` cards in hand; with `required`, one of them must contain that
    card (empty result if impossible). A bounded search: good, not always optimal."""
    avail = Counter(_norm(c) for c in hand)
    budget = len(hand) - keep
    cands = [list(m) for m in candidates if score(m) > 0]
    cands.sort(key=lambda m: (-score(m), len(m)))
    scores = [score(m) for m in cands]
    needs = [Counter(_norm(c) for c in m) for m in cands]
    suffix = [0] * (len(cands) + 1)
    for i in range(len(cands) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + scores[i]
    best: tuple[int, list[int]] = (0, [])
    nodes = 0

    def fits(need: Counter[str]) -> bool:
        return all(avail[k] >= v for k, v in need.items())

    def dfs(i: int, total: int, used: int, chosen: list[int]) -> None:
        nonlocal best, nodes
        nodes += 1
        if total > best[0]:
            best = (total, list(chosen))
        if i >= len(cands) or nodes > node_cap or total + suffix[i] <= best[0]:
            return
        need = needs[i]
        if used + len(cands[i]) <= budget and fits(need):
            avail.subtract(need)
            chosen.append(i)
            dfs(i + 1, total + scores[i], used + len(cands[i]), chosen)
            chosen.pop()
            avail.update(need)
        dfs(i + 1, total, used, chosen)

    if required is None:
        dfs(0, 0, 0, [])
    else:
        # Start from each candidate holding the required card, so every result contains it.
        key = _norm(required)
        for i, m in enumerate(cands):
            if key in needs[i] and len(m) <= budget and fits(needs[i]):
                nodes = 0
                avail.subtract(needs[i])
                dfs(0, scores[i], len(m), [i])
                avail.update(needs[i])
    return _with_jokers(hand, [cands[j] for j in best[1]])


def _with_jokers(hand: Sequence[str], melds: list[list[str]]) -> list[list[str]]:
    """Give each joker placeholder an actual joker code from the hand."""
    spare = sorted(c for c in hand if is_joker(c))
    out: list[list[str]] = []
    for m in melds:
        row = []
        for c in m:
            row.append(spare.pop(0) if is_joker(c) else c)
        out.append(row)
    return out
