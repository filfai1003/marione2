import random
import time

import chess
import pytest

from marione.games.base import IllegalMove
from marione.games.chess_game import Chess, evaluate
from tests.games.helpers import play_out

MODE = Chess.modes[0]


def new_game(fen: str | None = None, **options: object) -> Chess:
    game = Chess(MODE, random.Random(1), dict(options))
    if fen is not None:
        game.board = chess.Board(fen)
    return game


def play(game: Chess, *ucis: str) -> None:
    for uci in ucis:
        game.act(game.to_act()[0], {"type": "move", "uci": uci})


def test_start_and_legal_moves() -> None:
    game = new_game()
    assert game.to_act() == [0]
    legal = game.legal(0)
    moves = [a for a in legal if a["type"] == "move"]
    assert len(moves) == 20
    assert {"type": "resign"} in legal and {"type": "offer_draw"} in legal
    assert game.legal(1) == []
    view = game.view(None)
    assert view["turn"] == "w" and view["lastMove"] is None and view["result"] is None
    assert sorted(view["legalBySquare"]["g1"]) == ["f3", "h3"]
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "move", "uci": "e2e5"})
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "move", "uci": "e7e5"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "move", "uci": "garbage"})
    play(game, "e2e4", "d7d5", "e4d5")
    view = game.view(0)
    assert view["moves"] == ["e4", "d5", "exd5"]
    assert view["captured"] == {"w": ["p"], "b": []}
    assert view["lastMove"] == "e4d5" and view["turn"] == "b"


def test_promotion() -> None:
    game = new_game("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    assert {"type": "move", "uci": "e7e8q"} in game.legal(0)
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "move", "uci": "e7e8"})
    play(game, "e7e8n")
    assert game.board.piece_at(chess.E8) == chess.Piece(chess.KNIGHT, chess.WHITE)
    assert game.view(None)["moves"] == ["e8=N"]


def test_fools_mate() -> None:
    game = new_game()
    play(game, "f2f3", "e7e5", "g2g4", "d8h4")
    assert game.finished and game.winners() == [1] and game.to_act() == []
    view = game.view(None)
    assert view["result"] == "0-1" and view["reason"] == "checkmate" and view["check"]
    assert view["legalBySquare"] == {} and game.legal(0) == []
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "resign"})


def test_stalemate() -> None:
    game = new_game("7k/8/6Q1/8/8/8/8/K7 w - - 0 1")
    play(game, "g6f7")
    assert game.finished and game.winners() == []
    assert game.view(None)["result"] == "1/2-1/2" and game.reason == "stalemate"


def test_insufficient_material_and_repetition() -> None:
    game = new_game("8/8/8/8/8/2k5/7p/K4N2 w - - 0 1")
    play(game, "f1h2")
    assert game.reason == "material"
    game = new_game()
    play(game, "g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8")
    assert game.reason == "repetition" and game.winners() == []


def test_resign_any_time() -> None:
    game = new_game()
    game.act(1, {"type": "resign"})  # not black's turn, still allowed
    assert game.winners() == [0] and game.result == "1-0" and game.reason == "resign"


def test_draw_offer_flow() -> None:
    game = new_game()
    game.act(0, {"type": "offer_draw"})
    assert game.to_act() == [1] and game.view(None)["drawOffer"] == 0
    assert game.legal(1) == [{"type": "accept_draw"}, {"type": "decline_draw"}]
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "move", "uci": "e7e5"})
    game.act(1, {"type": "decline_draw"})
    assert game.to_act() == [0] and game.view(None)["drawOffer"] is None
    assert {"type": "offer_draw"} not in game.legal(0)  # once every 10 plies
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "offer_draw"})
    play(game, "e2e4", "e7e5")
    play(game, "g1f3")
    game.act(1, {"type": "offer_draw"})
    game.act(0, {"type": "accept_draw"})
    assert game.finished and game.winners() == [] and game.reason == "draw_agreed"


def test_bot_answers_draw_offers_by_eval() -> None:
    # White is a queen up: black's bot accepts, white's bot declines.
    game = new_game("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
    game.act(0, {"type": "offer_draw"})
    assert game.bot_action(1) == {"type": "accept_draw"}
    game = new_game("4k3/8/8/8/8/8/8/3QK3 b - - 0 1")
    game.act(1, {"type": "offer_draw"})
    assert game.bot_action(0) == {"type": "decline_draw"}


@pytest.mark.parametrize("level", [1, 3, 5])
def test_bot_finds_mate_in_one(level: int) -> None:
    # Back-rank mate: Ra8#.
    fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    for seed in range(3):
        game = Chess(MODE, random.Random(seed), {"level": level})
        game.board = chess.Board(fen)
        if level == 1:
            # Level 1 blunders on purpose sometimes: force the engine path.
            game.rng = random.Random(0)
            game.rng.random = lambda: 1.0  # type: ignore[method-assign]
        assert game.bot_action(0) == {"type": "move", "uci": "a1a8"}


def test_bot_takes_a_free_queen() -> None:
    game = new_game("4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1", level=3)
    assert game.bot_action(0) == {"type": "move", "uci": "d1d5"}


def test_bot_thinks_within_budget() -> None:
    fen = "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP1B1PPP/R2QKB1R w KQ - 0 9"
    game = new_game(fen, level=5)
    start = time.monotonic()
    action = game.bot_action(0)
    assert time.monotonic() - start < 2.5
    assert action in game.legal(0)


def test_evaluate_is_symmetric() -> None:
    board = chess.Board()
    assert evaluate(board) == 0
    board.push_uci("e2e4")
    assert evaluate(board) < 0  # black to move, white is better placed


@pytest.mark.parametrize("seed", range(2))
def test_bots_play_a_full_game(seed: int) -> None:
    game = play_out(Chess, MODE, seed, {"level": 1, "max_plies": 300})
    assert isinstance(game, Chess)
    assert game.result in ("1-0", "0-1", "1/2-1/2")
    assert game.reason is not None
    assert len(game.view(None)["moves"]) <= 300
