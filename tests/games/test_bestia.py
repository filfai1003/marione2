import random

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.bestia import Bestia, beats
from tests.games.helpers import play_out

THREE = Bestia.modes[0]


def _game(hands: list[list[str]], trump: str = "1s", strict: bool = True) -> Bestia:
    game = Bestia(THREE, random.Random(0), {"strict": strict})
    game.hands = hands
    game.trump_card, game.trump = trump, trump[1]
    return game


def test_strength() -> None:
    assert beats("1d", "Rd", "s") and beats("Rd", "7d", "s") and not beats("2d", "3d", "s")
    assert beats("2s", "1d", "s") and not beats("1c", "2d", "s")


def test_follow_suit_and_must_beat() -> None:
    game = _game([["5d", "7c", "2b"], ["4d", "Rd", "1s"], ["6c", "2s", "Cb"]])
    game.act(0, {"type": "play", "card": "5d"})
    assert [a["card"] for a in game.legal(1)] == ["Rd"]
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "play", "card": "4d"})
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "play", "card": "1s"})
    game.act(1, {"type": "play", "card": "Rd"})
    # no denari: must trump
    assert [a["card"] for a in game.legal(2)] == ["2s"]
    game.act(2, {"type": "play", "card": "2s"})
    assert game.tricks == [0, 0, 1] and game.turn == 2


def test_not_strict_allows_any_card_of_suit() -> None:
    game = _game([["5d", "7c", "2b"], ["4d", "Rd", "1s"], ["6c", "2s", "Cb"]], strict=False)
    game.act(0, {"type": "play", "card": "5d"})
    assert {a["card"] for a in game.legal(1)} == {"4d", "Rd"}


def test_overtrump_when_possible() -> None:
    game = _game([["5d", "7c", "2b"], ["3s", "Rc", "1c"], ["6c", "2s", "Cs"]])
    game.act(0, {"type": "play", "card": "5d"})
    game.act(1, {"type": "play", "card": "3s"})
    assert [a["card"] for a in game.legal(2)] == ["Cs"]


def test_cannot_beat_trumped_trick_follows_any() -> None:
    game = _game([["5d", "7c", "2b"], ["3s", "Rc", "1c"], ["6d", "4d", "Cs"]])
    game.act(0, {"type": "play", "card": "5d"})
    game.act(1, {"type": "play", "card": "3s"})
    assert {a["card"] for a in game.legal(2)} == {"6d", "4d"}


@pytest.mark.parametrize("mode", Bestia.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(8))
def test_full_round_split(mode: Mode, seed: int) -> None:
    game = play_out(Bestia, mode, seed)
    assert isinstance(game, Bestia)
    split = game.split()
    assert sum(split.values()) == 3 and all(n > 0 for n in split.values())
    assert sorted(game.bestia() + list(split)) == list(range(mode.seats))
    assert game.view(None)["bestia"] == game.bestia() and game.view(0)["turn"] is None
    assert game.summary()["tricks"] == game.tricks


def test_view_hides_hands() -> None:
    game = Bestia(Bestia.modes[1], random.Random(2))
    v = game.view(None)
    assert v["hand"] == [] and v["handCounts"] == [3, 3, 3, 3] and v["bestia"] == []
    assert game.view(1)["hand"] == game.hands[1] and v["trump"][1] == game.trump
