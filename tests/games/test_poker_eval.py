import pytest

from marione.games.poker_eval import best_five, evaluate, evaluate5


def name(cards: str) -> str:
    return evaluate(cards.split())[1]


def rank(cards: str) -> tuple[int, tuple[int, ...]]:
    return evaluate(cards.split())[0]


@pytest.mark.parametrize(
    ("cards", "expected"),
    [
        ("Ah Kh Qh Jh Th", "royal_flush"),
        ("9s 8s 7s 6s 5s", "straight_flush"),
        ("5d 4d 3d 2d Ad", "straight_flush"),
        ("7c 7d 7h 7s 2c", "four"),
        ("Kc Kd Kh 3s 3c", "full_house"),
        ("2h 9h Jh 4h Kh", "flush"),
        ("Ts 9h 8d 7c 6s", "straight"),
        ("Ah 2c 3d 4s 5h", "straight"),
        ("Ah Kc Qd Js Th", "straight"),
        ("Qs Qh Qd 5c 2s", "three"),
        ("Js Jh 4d 4c As", "two_pair"),
        ("9s 9h 4d 3c As", "pair"),
        ("As Jh 8d 4c 2s", "high_card"),
        ("Kh Ah 2c 3d 4s", "high_card"),  # no wrap-around straight
        ("Ah Kh Qh Jh Th 9h 8h", "royal_flush"),
        ("2c 3c 4c 5c 7d 6c Ac", "straight_flush"),
        ("As Ad Ah Ks Kd Kh 2c", "full_house"),
        ("As Ad Ks Kd Qs Qd 2c", "two_pair"),
        ("2s 3s 4s 5s 9s 6d 7d", "flush"),
        ("8c 8d 8h 8s 2d 2h 2c", "four"),
        ("Jc 9d 6h 5s 3c 2d 4h", "straight"),
    ],
)
def test_names(cards: str, expected: str) -> None:
    assert name(cards) == expected


@pytest.mark.parametrize(
    ("better", "worse"),
    [
        ("Ah Kh Qh Jh Th", "9s 8s 7s 6s 5s"),
        ("6s 5s 4s 3s 2s", "5d 4d 3d 2d Ad"),
        ("2c 2d 2h 2s 3c", "Ac Ad Ah Kc Kd"),
        ("3c 3d 3h 2s 2c", "2c 2d 2h As Ac"),
        ("Ah 9h 8h 4h 3h", "Kh Qh Jh 9h 7h"),
        ("2h 3h 4h 5h 7h", "Ts 9h 8d 7c 6s"),
        ("6s 5h 4d 3c 2s", "5h 4d 3c 2s Ah"),
        ("Ts 9h 8d 7c 6s", "As Ad Ah Kc 2d"),
        ("Ks Kh Kd 2c 3s", "Qs Qh Qd Ac Ks"),
        ("As Ah 3d 3c 2s", "Ks Kh Qd Qc As"),
        ("Ks Kh Qd Qc 3s", "Ks Kh Qd Qc 2s"),
        ("As Ah Kd 4c 3s", "As Ah Qd Jc Ts"),
        ("As Kh 9d 4c 3s", "As Kh 9d 4c 2s"),
        ("2s 2h 3d 4c 5s", "Ah Kd Qc Js 9h"),
    ],
)
def test_order(better: str, worse: str) -> None:
    assert rank(better) > rank(worse)


def test_ties_and_best_five() -> None:
    assert rank("Ah Kh Qh Jh 9h") == rank("As Ks Qs Js 9s")
    assert rank("As Ah 7d 6c 2s 3h 4h") == rank("Ac Ad 7h 6s 2d 3s 4c")
    # Board plays: both have the straight on the board.
    board = "Ts 9h 8d 7c 6s"
    assert rank(board + " 2c 2d") == rank(board + " 3h 4c")
    r, five = best_five(["2c", "3c", "4c", "5c", "7d", "6c", "Ac"])
    assert set(five) == {"2c", "3c", "4c", "5c", "6c"}
    assert r == evaluate5(five)


def test_bad_sizes() -> None:
    with pytest.raises(ValueError, match="5 to 7"):
        evaluate(["Ah", "Kh"])
    with pytest.raises(ValueError, match="five"):
        evaluate5(["Ah", "Kh"])
