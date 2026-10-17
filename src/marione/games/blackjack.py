"""Blackjack against the bank, one round per game, a fresh 6-deck shoe each round.

The player bets, gets two cards; the dealer gets one up and one hole card. With an ace or a ten
up the dealer peeks: a dealer blackjack ends the round at once (a player blackjack then pushes).
A player blackjack pays 3 to 2. The player may hit, stand, double (first two cards of a hand,
one more card) and split once (two cards of the same rank; split aces get one card each, and
21 after a split is not a blackjack). The dealer draws to 17 and stands on soft 17. A push
gives the bet back. No insurance.
"""

import random
from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode
from marione.games.cards import french_deck, rank, shuffled

DECKS = 6
MAX_BET = 100_000
HIDDEN = "??"


def card_value(card: str) -> int:
    r = rank(card)
    if r == "A":
        return 11
    if r in "TJQK":
        return 10
    return int(r)


def hand_total(cards: list[str]) -> tuple[int, bool]:
    """(best total, soft): soft when an ace still counts 11."""
    total = sum(card_value(c) for c in cards)
    aces = sum(1 for c in cards if rank(c) == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def is_blackjack(cards: list[str]) -> bool:
    return len(cards) == 2 and hand_total(cards)[0] == 21


class Hand:
    def __init__(self, cards: list[str], bet: int, split: bool = False) -> None:
        self.cards = cards
        self.bet = bet
        self.split = split  # born from a split: 21 is not a blackjack
        self.doubled = False
        self.done = False
        self.result: str | None = None

    @property
    def total(self) -> int:
        return hand_total(self.cards)[0]

    @property
    def natural(self) -> bool:
        return not self.split and is_blackjack(self.cards)


class Blackjack(Game):
    key: ClassVar[str] = "blackjack"
    modes: ClassVar[tuple[Mode, ...]] = (Mode("solo", 1),)
    economy = "bets"
    house = True

    def __init__(
        self, mode: Mode, rng: random.Random, options: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mode, rng, options)
        self.max_bet = min(MAX_BET, max(1000, 50 * self.stake))
        self.shoe = shuffled(french_deck(DECKS), rng)
        self.phase = "bet"  # bet | play | done
        self.hands: list[Hand] = []
        self.active = 0
        self.dealer: list[str] = []
        self.revealed = False

    # --- rules -------------------------------------------------------------------------------

    def _draw(self) -> str:
        return self.shoe.pop()

    def _hand(self) -> Hand:
        return self.hands[self.active]

    def _can_double(self) -> bool:
        h = self._hand()
        return len(h.cards) == 2 and not h.done

    def _can_split(self) -> bool:
        h = self._hand()
        return (
            len(self.hands) == 1
            and len(h.cards) == 2
            and rank(h.cards[0]) == rank(h.cards[1])
            and not h.done
        )

    def to_act(self) -> list[int]:
        return [] if self.finished else [0]

    def legal(self, seat: int) -> list[Action]:
        if seat != 0 or self.finished:
            return []
        if self.phase == "bet":
            return [{"type": "bet", "min": 1, "max": self.max_bet}]
        out: list[Action] = [{"type": "hit"}, {"type": "stand"}]
        if self._can_double():
            out.append({"type": "double"})
        if self._can_split():
            out.append({"type": "split"})
        return out

    def cost(self, seat: int, action: Action) -> int:
        if seat != 0 or self.finished:
            raise IllegalMove("not now")
        kind = action.get("type")
        if self.phase == "bet":
            if kind != "bet":
                raise IllegalMove("place a bet first")
            return self._amount(action)
        if kind == "double":
            if not self._can_double():
                raise IllegalMove("cannot double now")
            return self._hand().bet
        if kind == "split":
            if not self._can_split():
                raise IllegalMove("cannot split now")
            return self._hand().bet
        if kind in ("hit", "stand"):
            return 0
        raise IllegalMove("unknown action")

    def _amount(self, action: Action) -> int:
        amount = action.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise IllegalMove("bad amount")
        if not 1 <= amount <= self.max_bet:
            raise IllegalMove("bet out of range")
        return amount

    def act(self, seat: int, action: Action) -> None:
        self.cost(seat, action)  # the same checks
        kind = action["type"]
        if kind == "bet":
            self._deal(self._amount(action))
            return
        h = self._hand()
        if kind == "hit":
            h.cards.append(self._draw())
            self.log.add("hit", seat=0, card=h.cards[-1])
            if h.total >= 21:
                h.done = True
        elif kind == "stand":
            h.done = True
            self.log.add("stand", seat=0)
        elif kind == "double":
            h.bet *= 2
            h.doubled = True
            h.cards.append(self._draw())
            h.done = True
            self.log.add("double", seat=0, card=h.cards[-1])
        elif kind == "split":
            a, b = h.cards
            aces = rank(a) == "A"
            self.hands = [
                Hand([a, self._draw()], h.bet, True),
                Hand([b, self._draw()], h.bet, True),
            ]
            self.log.add("split", seat=0)
            for nh in self.hands:
                if aces or nh.total >= 21:
                    nh.done = True
        self._advance()

    def _deal(self, bet: int) -> None:
        player = [self._draw()]
        self.dealer = [self._draw()]
        player.append(self._draw())
        self.dealer.append(self._draw())
        self.hands = [Hand(player, bet)]
        self.phase = "play"
        self.log.add("deal", seat=0, bet=bet)
        if is_blackjack(self.dealer):
            self.log.add("dealer_blackjack")  # the peek: the round ends now
            self._finish(draw=False)
        elif is_blackjack(player):
            self._finish(draw=False)

    def _advance(self) -> None:
        while self.active < len(self.hands) and self.hands[self.active].done:
            self.active += 1
        if self.active >= len(self.hands):
            self.active = len(self.hands) - 1
            alive = any(h.total <= 21 and not h.natural for h in self.hands)
            self._finish(draw=alive)

    def _finish(self, draw: bool) -> None:
        self.revealed = True
        if draw:
            while True:
                if hand_total(self.dealer)[0] >= 17:  # stands on soft 17 too
                    break
                self.dealer.append(self._draw())
        dealer_total = hand_total(self.dealer)[0]
        dealer_bj = is_blackjack(self.dealer)
        for h in self.hands:
            h.done = True
            if h.total > 21:
                h.result = "bust"
            elif h.natural:
                h.result = "push" if dealer_bj else "blackjack"
            elif dealer_bj:
                h.result = "lose"
            elif dealer_total > 21 or h.total > dealer_total:
                h.result = "win"
            elif h.total == dealer_total:
                h.result = "push"
            else:
                h.result = "lose"
        self.phase = "done"
        self.log.add("result", dealer=dealer_total, results=[h.result for h in self.hands])

    @property
    def finished(self) -> bool:
        return self.phase == "done"

    @staticmethod
    def gross(h: Hand) -> int:
        if h.result == "blackjack":
            return h.bet + h.bet * 3 // 2
        if h.result == "win":
            return 2 * h.bet
        if h.result == "push":
            return h.bet
        return 0

    def payouts(self) -> dict[int, int]:
        return {0: sum(self.gross(h) for h in self.hands)} if self.finished else {}

    def summary(self) -> dict[str, Any]:
        return {
            "results": [h.result for h in self.hands],
            "dealer": hand_total(self.dealer)[0] if self.dealer else 0,
            "win": sum(self.gross(h) for h in self.hands),
        }

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        if self.phase == "bet":
            return {"type": "bet", "amount": min(self.max_bet, max(1, self.stake))}
        h = self._hand()
        up = card_value(self.dealer[0])
        total, soft = hand_total(h.cards)
        if self._can_split() and rank(h.cards[0]) in "A8":
            return {"type": "split"}
        if self._can_double() and not soft and total in (10, 11) and up < total:
            return {"type": "double"}
        if soft:
            return {"type": "hit"} if total <= 17 else {"type": "stand"}
        if total <= 11 or (total < 17 and up >= 7) or (total == 12 and up <= 3):
            return {"type": "hit"}
        return {"type": "stand"}

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        hands = []
        for h in self.hands:
            total, soft = hand_total(h.cards)
            hands.append(
                {
                    "cards": list(h.cards),
                    "total": total,
                    "soft": soft,
                    "bet": h.bet,
                    "doubled": h.doubled,
                    "done": h.done,
                    "result": h.result,
                }
            )
        if self.revealed:
            dealer_cards = list(self.dealer)
            dealer_total, dealer_soft = hand_total(self.dealer)
        elif self.dealer:
            dealer_cards = [self.dealer[0], HIDDEN]
            dealer_total, dealer_soft = hand_total(self.dealer[:1])
        else:
            dealer_cards, dealer_total, dealer_soft = [], 0, False
        return {
            "phase": self.phase,
            "hands": hands,
            "active": self.active if self.phase == "play" else None,
            "dealer": {
                "cards": dealer_cards,
                "total": dealer_total,
                "soft": dealer_soft,
                "revealed": self.revealed,
            },
            "maxBet": self.max_bet,
            "win": sum(self.gross(h) for h in self.hands) if self.finished else 0,
            "shoe": len(self.shoe),
        }
