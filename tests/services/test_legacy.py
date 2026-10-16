import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from marione.db.ledger import Ledger
from marione.db.pool import Pool
from marione.db.soundboard import SoundboardRepo
from marione.db.sounds import SoundsRepo
from marione.dev.preview import tone
from marione.domain.presence import choose_channel
from marione.services.legacy import (
    LegacyImporter,
    entrance_name,
    parse_board,
    parse_economy,
    parse_entrance,
    parse_settings,
    tier_key_for_name,
)


@dataclass
class Att:
    filename: str
    data: bytes

    async def read(self) -> bytes:
        return self.data


@dataclass
class Msg:
    id: int
    content: str
    attachments: list[Att] = field(default_factory=list)


def js(obj: object, name: str = "x.json") -> list[Att]:
    return [Att(name, json.dumps(obj).encode())]


async def feed(messages: list[Msg]) -> AsyncIterator[Msg]:
    for m in messages:
        yield m


class TestParsers:
    def test_board_both_formats(self) -> None:
        assert parse_board("MARIONE_SB|12|👏|1500|Applausi forti") == parse_board(
            "MARIONE_SB|12|👏|Applausi forti"
        )
        entry = parse_board("MARIONE_SB|12|👏|1500|Applausi forti")
        assert entry is not None and (entry.creator, entry.emoji, entry.name) == (
            12,
            "👏",
            "Applausi forti",
        )
        assert parse_board("MARIONE_SB|x|y|z") is None
        assert parse_board("MARIONE|12") is None
        assert parse_board("MARIONE_SB|12|🔊|   ") is None

    def test_entrance(self) -> None:
        assert parse_entrance("MARIONE|123") == 123
        assert parse_entrance("MARIONE|abc") is None
        assert parse_entrance("MARIONE_SB|1|2|3") is None
        assert entrance_name("123_squillo_di_tromba.mp3", 123) == "squillo di tromba"
        assert entrance_name("123_123_x.mp3", 123) == "x"
        assert entrance_name("123_.mp3", 123) == "audio"

    def test_economy_and_settings(self) -> None:
        econ = parse_economy(
            {"bal": {"1": 50, "2": "7", "x": 3, "3": "bad"}, "names": {"1": "Ugo"}}
        )
        assert econ == {1: (50, "Ugo"), 2: (7, "")}
        assert parse_economy("nope") == {}
        favs, roles = parse_settings(
            {"fav_sounds": {"1": [10, 11]}, "wealth_roles": {"Morto di fame": 99}}
        )
        assert favs == {1: {10, 11}} and roles == {"Morto di fame": 99}
        assert parse_settings({"fav_sounds": [1, 2]}) == ({}, {})
        assert tier_key_for_name("morto di FAME") == "morto-di-fame"
        assert tier_key_for_name("Nobody") is None


class TestImporter:
    def messages(self) -> list[Msg]:
        return [
            Msg(1, "MARIONE_ECON", js({"bal": {"1": 10}, "names": {"1": "Vecchio"}})),
            Msg(2, "MARIONE_SB|1|👏|600|Applausi", [Att("sb_1.mp3", tone(440, 0.6))]),
            Msg(3, "MARIONE_SB|2|🥁|Rullo", [Att("sb_2.mp3", tone(200, 0.4))]),
            Msg(4, "MARIONE|1", [Att("1_squillo.mp3", tone(500, 0.5))]),
            Msg(5, "MARIONE|1", [Att("1_squillo.mp3", tone(520, 0.5))]),  # same name
            Msg(6, "MARIONE_SB|1|🗑|Rotto", [Att("sb.mp3", b"not audio")]),
            Msg(7, "chiacchiere", []),
            Msg(8, "MARIONE_ECON", js({"bal": {"1": 900, "2": 40}, "names": {"1": "Ugo"}})),
            Msg(
                9,
                "MARIONE_SETTINGS",
                js({"fav_sounds": {"2": [2, 99]}, "wealth_roles": {"Morto di fame": 77}}),
            ),
        ]

    async def test_imports_everything_once(self, pool: Pool) -> None:
        ledger = Ledger(pool)
        importer = LegacyImporter(pool, ledger, SoundboardRepo(pool), SoundsRepo(pool))
        report = await importer.run(feed(self.messages()))
        # The newest economy snapshot wins.
        assert await ledger.balance(1) == 900 and await ledger.balance(2) == 40
        assert await ledger.name_of(1) == "Ugo"
        assert report.balances == 2 and report.coins == 940
        assert report.board == 2 and report.entrances == 2 and report.favorites == 1
        assert len(report.skipped) == 1 and "Rotto" in report.skipped[0]
        assert report.old_roles == {"morto-di-fame": 77}
        board = await SoundboardRepo(pool).catalog(2)
        assert [s.name for s in board if s.fav] == ["Applausi"]  # old message 2, member 2
        names = [s.name for s in await SoundsRepo(pool).list(1)]
        assert names == ["squillo", "squillo 2"]
        history = await ledger.history(1, 5)
        assert history[0].reason == "legacy_import"
        assert await ledger.audit() == []

        again = await importer.run(feed(self.messages()))
        assert (again.coins, again.board, again.entrances) == (0, 0, 0)
        assert await ledger.balance(1) == 900
        assert len(await SoundboardRepo(pool).catalog(1)) == 2

    async def test_long_old_sounds_are_kept(self, pool: Pool) -> None:
        importer = LegacyImporter(pool, Ledger(pool), SoundboardRepo(pool), SoundsRepo(pool))
        report = await importer.run(
            feed([Msg(1, "MARIONE_SB|1|📯|Lungo", [Att("a.wav", tone(300, 45))])])
        )
        assert report.board == 1


class TestPresence:
    @pytest.mark.parametrize(
        ("current", "channels", "joined", "expected"),
        [
            (None, {1: 0, 2: 0}, None, None),  # nobody anywhere: stay out
            (None, {1: 1}, 1, 1),  # someone joins: go there
            (1, {1: 2, 2: 1}, 2, 1),  # people still with the bot: stay
            (1, {1: 0, 2: 1}, None, 2),  # left alone: go to the others
            (1, {1: 0, 2: 0}, None, None),  # left alone, nobody else: leave
            (None, {1: 1, 2: 3}, None, 2),  # at start: the busiest channel
            (1, {1: 0, 2: 1, 3: 1}, 3, 3),  # alone and someone just joined 3
        ],
    )
    def test_choose_channel(
        self,
        current: int | None,
        channels: dict[int, int],
        joined: int | None,
        expected: int | None,
    ) -> None:
        assert choose_channel(current, channels, joined) == expected
