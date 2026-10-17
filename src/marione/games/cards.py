"""Decks of cards as two-character codes, so states stay plain JSON.

French cards: rank + suit. Ranks ``23456789TJQKA``, suits ``s`` spades, ``h`` hearts,
``d`` diamonds, ``c`` clubs ("Ah", "Td"). Jokers are "X1".."X4" (no suit).

Italian (Piacentine/Napoletane, 40 cards): rank + suit. Ranks ``1234567`` then ``F`` fante (8),
``C`` cavallo (9), ``R`` re (10); suits ``d`` denari, ``c`` coppe, ``b`` bastoni, ``s`` spade
("1d" is the asso di denari, "Rs" the re di spade, "7d" the settebello).
"""

import random

FR_RANKS = "23456789TJQKA"
FR_SUITS = "shdc"
IT_RANKS = "1234567FCR"
IT_SUITS = "dcbs"


def french_deck(copies: int = 1, jokers: int = 0) -> list[str]:
    deck = [r + s for _ in range(copies) for s in FR_SUITS for r in FR_RANKS]
    deck += [f"X{i + 1}" for i in range(jokers)]
    return deck


def italian_deck() -> list[str]:
    return [r + s for s in IT_SUITS for r in IT_RANKS]


def shuffled(deck: list[str], rng: random.Random) -> list[str]:
    cards = list(deck)
    rng.shuffle(cards)
    return cards


def rank(card: str) -> str:
    return card[0]


def suit(card: str) -> str:
    return card[1]


def is_joker(card: str) -> bool:
    return card[0] == "X"


def fr_value(card: str) -> int:
    """2..14 (ace high)."""
    return FR_RANKS.index(card[0]) + 2


def it_number(card: str) -> int:
    """1..10: asso 1, ..., 7, fante 8, cavallo 9, re 10."""
    return IT_RANKS.index(card[0]) + 1


def take(hand: list[str], card: str) -> None:
    """Remove one copy of `card` from `hand` (ValueError if it is not there)."""
    hand.remove(card)
