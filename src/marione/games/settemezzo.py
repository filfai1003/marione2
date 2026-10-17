"""Sette e mezzo against the bank (Marione), one round per game.

The player bets, gets a first card face down (only they see it) and then draws face-up cards or
stands; over 7.5 is a bust. Cards 1-7 count their number, figures (fante, cavallo, re) half a
point; the re di denari is the matta, worth whatever helps most (decided at the end). The bank
reveals its hidden card and draws while under 5.5 and not already ahead; ties go to the bank.
A win pays 1:1, a "sette e mezzo reale" (a 7 and a figure, two cards only) pays 2:1.
"""

from typing import Any, ClassVar, Literal

from marione.games.base import Action, Game, IllegalMove, Mode
from marione.games.cards import italian_deck, shuffled

MAX_BET = 5000
MATTA = "Rd"
HIDDEN = "??"
BANK_STANDS = 5.5

Phase = Literal["bet", "play", "done"]
Result = Literal["win", "lose", "reale", "bust"]


def card_value(card: str) -> float:
    return float(card[0]) if card[0] in "1234567" else 0.5


def total(cards: list[str]) -> float:
    """Best total ≤ 7.5 (the matta takes the value that helps most), or the bust total."""
    base = sum(card_value(c) for c in cards if c != MATTA)
    if MATTA not in cards:
        return base
    options = [0.5, *range(1, 8)]
    good = [base + v for v in options if base + v <= 7.5]
    return max(good) if good else base + 0.5


def is_reale(cards: list[str]) -> bool:
    return len(cards) == 2 and any(c[0] == "7" for c in cards) and total(cards) == 7.5


class SetteMezzo(Game):
    key: ClassVar[str] = "settemezzo"
    modes: ClassVar[tuple[Mode, ...]] = (Mode("solo", 1),)
    economy: ClassVar[Literal["stake", "bets"]] = "bets"
    house: ClassVar[bool] = True

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        self.deck = shuffled(italian_deck(), rng)
        self.phase: Phase = "bet"
        self.bet = 0
        self.cards: list[str] = []
        self.bank: list[str] = []
        self.bank_played = False
        self.result: Result | None = None

    # --- rules -------------------------------------------------------------------------------

    def to_act(self) -> list[int]:
        return [] if self.phase == "done" else [0]

    def legal(self, seat: int) -> list[Action]:
        if seat != 0 or self.phase == "done":
            return []
        if self.phase == "bet":
            return [{"type": "bet", "min": 1, "max": MAX_BET}]
        return [{"type": "card"}, {"type": "stand"}]

    def cost(self, seat: int, action: Action) -> int:
        if self.phase == "bet" and action.get("type") == "bet":
            amount = action.get("amount")
            if isinstance(amount, int) and not isinstance(amount, bool):
                return amount
        return 0

    def act(self, seat: int, action: Action) -> None:
        kind = action.get("type")
        if seat != 0 or self.phase == "done":
            raise IllegalMove("not your turn")
        if self.phase == "bet":
            amount = action.get("amount")
            if kind != "bet" or not isinstance(amount, int) or isinstance(amount, bool):
                raise IllegalMove("bet first")
            if not 1 <= amount <= MAX_BET:
                raise IllegalMove("bad amount")
            self.bet = amount
            self.cards.append(self.deck.pop())
            self.bank.append(self.deck.pop())
            self.phase = "play"
            self.log.add("bet", seat=0, amount=amount)
            self._check_player()
        elif kind == "card":
            card = self.deck.pop()
            self.cards.append(card)
            self.log.add("card", seat=0, card=card)
            self._check_player()
        elif kind == "stand":
            self.log.add("stand", seat=0, total=total(self.cards))
            self._bank_plays()
        else:
            raise IllegalMove("unknown action")

    def _check_player(self) -> None:
        t = total(self.cards)
        if t > 7.5:
            self.result = "bust"
            self.phase = "done"
            self.bank_played = True  # nothing left hidden
            self.log.add("bust", seat=0, total=t)
        elif t == 7.5:
            self._bank_plays()  # nothing better to draw for

    def _bank_plays(self) -> None:
        self.bank_played = True
        player = total(self.cards)
        while total(self.bank) < BANK_STANDS and total(self.bank) < player:
            self.bank.append(self.deck.pop())
        bank = total(self.bank)
        if bank > 7.5:
            self.log.add("bankBust", total=bank)
        reale = is_reale(self.cards)
        if bank > 7.5 or player > bank or (reale and not is_reale(self.bank)):
            self.result = "reale" if reale else "win"
        else:
            self.result = "lose"
        self.phase = "done"
        self.log.add("result", result=self.result, total=player, bank=bank)

    @property
    def finished(self) -> bool:
        return self.phase == "done"

    def payouts(self) -> dict[int, int]:
        if self.result == "reale":
            return {0: 3 * self.bet}
        if self.result == "win":
            return {0: 2 * self.bet}
        return {}

    def summary(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "bet": self.bet,
            "cards": list(self.cards),
            "total": total(self.cards),
            "bank": {"cards": list(self.bank), "total": total(self.bank)},
            "payout": self.payouts().get(0, 0),
        }

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        if self.phase == "bet":
            return {"type": "bet", "amount": min(MAX_BET, max(1, self.stake))}
        return {"type": "card"} if total(self.cards) < 5 else {"type": "stand"}

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        cards = list(self.cards)
        if seat != 0 and self.phase != "done" and cards:
            cards[0] = HIDDEN
        bank = list(self.bank)
        if not self.bank_played and bank:
            bank[0] = HIDDEN
        return {
            "phase": self.phase,
            "bet": self.bet,
            "cards": cards,
            "total": total([c for c in cards if c != HIDDEN]),
            "bank": {"cards": bank, "total": total([c for c in bank if c != HIDDEN])},
            "result": self.result,
            "payout": self.payouts().get(0, 0) if self.phase == "done" else None,
        }
