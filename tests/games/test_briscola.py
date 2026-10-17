import random

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.briscola import Briscola, beats, points
from tests.games.helpers import play_out


@pytest.mark.parametrize("mode", Briscola.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(6))
def test_bots_play_a_full_match_and_points_add_up(mode: Mode, seed: int) -> None:
    game = play_out(Briscola, mode, seed)
    assert isinstance(game, Briscola)
    assert sum(game.side_points()) == 120
    assert all(len(h) == 0 for h in game.hands)
    w = game.winners()
    assert w == [] or len(w) == (2 if mode.teams else 1)


def test_trick_rules() -> None:
    assert beats("3d", "Rd", "s") and not beats("Rd", "3d", "s")
    assert beats("2s", "1d", "s") and not beats("1c", "2d", "s")
    assert points("1b") == 11 and points("3b") == 10 and points("7b") == 0


def test_hidden_cards_and_turns() -> None:
    game = Briscola(Briscola.modes[0], random.Random(1))
    view = game.view(1)
    assert view["hand"] == game.hands[1] and view["handCounts"] == [3, 3]
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "play", "card": game.hands[1][0]})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "play", "card": game.hands[1][0]})
