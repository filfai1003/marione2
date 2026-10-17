from collections import Counter

import pytest

from marione.games.melds import (
    analyse,
    best_partition,
    card_points,
    find_melds,
    is_meld,
    meld_points,
)


@pytest.mark.parametrize(
    "cards",
    [
        ["7h", "7s", "7d"],
        ["7h", "7s", "7d", "7c"],
        ["Ah", "2h", "3h"],
        ["Qs", "Ks", "As"],
        ["3d", "4d", "5d", "6d", "7d", "8d"],
        ["2c", "3c", "4c", "5c", "6c", "7c", "8c", "9c", "Tc", "Jc", "Qc", "Kc", "Ac"],
        ["Ac", "2c", "3c", "4c", "5c", "6c", "7c", "8c", "9c", "Tc", "Jc", "Qc", "Kc"],
        ["5h", "3h", "4h"],  # any order
        ["7h", "7s", "X1"],
        ["7h", "7s", "7d", "X2"],
        ["5h", "X1", "7h"],
        ["5h", "6h", "X1"],
        ["X3", "2h", "3h"],
        ["Qs", "X1", "As"],
    ],
)
def test_valid_melds(cards: list[str]) -> None:
    assert is_meld(cards)


@pytest.mark.parametrize(
    "cards",
    [
        ["7h", "7s"],  # too short
        ["7h", "7h", "7d"],  # same suit twice in a set
        ["7h", "7s", "7d", "7c", "7h"],  # five in a set
        ["7h", "7s", "8d"],
        ["Kh", "Ah", "2h"],  # wrap-around
        ["5h", "6h", "8h"],  # gap
        ["5h", "6h", "6h", "7h"],  # duplicate in a run
        ["5h", "6s", "7h"],  # mixed suits
        ["5h", "X1", "X2"],  # two jokers (house rule)
        ["7h", "X1", "X2", "7s"],
        ["5h", "X1", "8h"],  # two gaps, one joker
        ["Ac", "2c", "3c", "4c", "5c", "6c", "7c", "8c", "9c", "Tc", "Jc", "Qc", "Kc", "X1"],
        ["Zh", "2h", "3h"],
        ["", "2h", "3h"],
    ],
)
def test_invalid_melds(cards: list[str]) -> None:
    assert not is_meld(cards)


def test_jokers_can_be_forbidden() -> None:
    assert not is_meld(["7h", "7s", "X1"], jokers=False)
    assert is_meld(["7h", "7s", "7c"], jokers=False)


def test_analysis_orders_runs_and_places_the_joker() -> None:
    m = analyse(["7h", "X1", "5h"])
    assert m is not None and m.kind == "run"
    assert m.cards == ("5h", "X1", "7h") and m.stands == ("5h", "6h", "7h")
    end = analyse(["5h", "6h", "X1"])
    assert end is not None and end.stands == ("5h", "6h", "7h")  # the higher reading
    top = analyse(["Qs", "Ks", "X1"])
    assert top is not None and top.stands == ("Qs", "Ks", "As")
    low = analyse(["2h", "3h", "Ah"])
    assert low is not None and low.cards == ("Ah", "2h", "3h")
    s = analyse(["7h", "7s", "X1"])
    assert s is not None and s.kind == "set" and s.stands[2][0] == "7"


def test_points() -> None:
    assert meld_points(["Ah", "2h", "3h"]) == 6
    assert meld_points(["Qh", "Kh", "Ah"]) == 31
    assert meld_points(["Ah", "As", "Ad"]) == 33
    assert meld_points(["Th", "Jh", "Qh"]) == 30
    assert meld_points(["5h", "X1", "7h"]) == 18
    assert meld_points(["Qh", "Kh", "X1"]) == 31  # the joker is the ace
    assert meld_points(["Kh", "Ks", "X2"]) == 30
    with pytest.raises(ValueError, match="not a meld"):
        meld_points(["2h", "9s", "Kd"])
    assert card_points("X1") == 25 and card_points("Ah") == 11 and card_points("Jd") == 10
    assert card_points("4c") == 4


def test_find_melds_and_partition() -> None:
    hand = ["7h", "7s", "7d", "8h", "9h", "Th", "2c", "Kd", "X1", "4s"]
    found = find_melds(hand)
    assert all(is_meld(m) for m in found)
    assert ["7h", "8h", "9h"] in found or ["7h", "8h", "9h", "Th"] in found
    best = best_partition(hand, found, meld_points, keep=1)
    used = Counter(c for m in best for c in m)
    assert all(used[c] <= Counter(hand)[c] for c in used)
    assert len(best) >= 2 and sum(map(len, best)) <= len(hand) - 1
    assert sum(meld_points(m) for m in best) >= 50


def test_partition_with_required_card() -> None:
    hand = ["7h", "7s", "7d", "Qc", "Kc", "Ac", "2d"]
    best = best_partition(hand, find_melds(hand), meld_points, keep=1, required="7d")
    assert any("7d" in m for m in best)
    none = best_partition(hand, find_melds(hand), meld_points, keep=1, required="2d")
    assert none == []


def test_partition_uses_duplicates_and_distinct_jokers() -> None:
    hand = ["5h", "5h", "6h", "6h", "X1", "X2", "2c"]
    best = best_partition(hand, find_melds(hand), meld_points, keep=1)
    assert len(best) == 2
    assert sorted(c for m in best for c in m if c.startswith("X")) == ["X1", "X2"]


def test_no_jokers_in_finder_when_forbidden() -> None:
    found = find_melds(["7h", "7s", "X1", "8h"], jokers=False)
    assert found == []
