"""Import from the old Marione, which kept its data as messages in a #marione-data channel:

    MARIONE_ECON      + economy.json   {"bal": {uid: n}, "names": {uid: name}}   (newest wins)
    MARIONE_SETTINGS  + settings.json  {"fav_sounds": {uid: [msg ids]}, "wealth_roles": {...}}
    MARIONE_SB|creator|emoji|duration_ms|name (or the older MARIONE_SB|creator|emoji|name) + audio
    MARIONE|uid       + audio            an entrance sound of that member

Every imported message is recorded in `marione.legacy_imports`, so running it again imports
nothing twice. The importer only reads: the old channel is never changed.
"""

import json
import logging
import re
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from marione import audio
from marione.db.ledger import Ledger
from marione.db.pool import Pool
from marione.db.soundboard import SoundboardRepo
from marione.db.sounds import SoundError, SoundsRepo
from marione.domain.roles import TIERS

logger = logging.getLogger("marione.legacy")

LEGACY_BOARD_MAX_MS = 120_000
LEGACY_ENTRANCE_MAX_MS = 120_000


class LegacyAttachment(Protocol):
    filename: str

    async def read(self) -> bytes: ...


class LegacyMessage(Protocol):
    id: int
    content: str

    @property
    def attachments(self) -> Sequence[LegacyAttachment]: ...


@dataclass(frozen=True)
class BoardEntry:
    creator: int
    emoji: str
    name: str


def parse_board(content: str) -> BoardEntry | None:
    if not content.startswith("MARIONE_SB|"):
        return None
    body = content[len("MARIONE_SB|") :]
    parts = body.split("|", 3)
    if len(parts) == 4 and parts[0].isdigit() and parts[2].isdigit():
        creator, emoji, _, name = parts
    else:
        parts = body.split("|", 2)
        if len(parts) < 3 or not parts[0].isdigit():
            return None
        creator, emoji, name = parts
    name = " ".join(name.split())[:40]
    if not name:
        return None
    return BoardEntry(int(creator), (emoji.strip() or "🔊")[:16], name)


def parse_entrance(content: str) -> int | None:
    match = re.fullmatch(r"MARIONE\|(\d+)", content.strip())
    return int(match.group(1)) if match else None


def entrance_name(filename: str, user_id: int) -> str:
    """'123_squillo.mp3' -> 'squillo'."""
    stem = filename.rsplit(".", 1)[0]
    prefix = f"{user_id}_"
    while stem.startswith(prefix):
        stem = stem[len(prefix) :]
    return (stem.replace("_", " ").strip() or "audio")[:60]


def parse_economy(data: Any) -> dict[int, tuple[int, str]]:
    """uid -> (balance, last known name)."""
    if not isinstance(data, dict):
        return {}
    balances = data.get("bal", {}) or {}
    names = data.get("names", {}) or {}
    out: dict[int, tuple[int, str]] = {}
    for key in set(balances) | set(names):
        if not str(key).isdigit():
            continue
        try:
            balance = max(0, int(balances.get(key, 0)))
        except (TypeError, ValueError):
            continue
        out[int(key)] = (balance, str(names.get(key, "") or ""))
    return out


def parse_settings(data: Any) -> tuple[dict[int, set[int]], dict[str, int]]:
    """(favourites: uid -> old soundboard message ids, wealth roles: tier name -> role id)."""
    if not isinstance(data, dict):
        return {}, {}
    favs: dict[int, set[int]] = {}
    raw = data.get("fav_sounds", {})
    if isinstance(raw, dict):
        for uid, ids in raw.items():
            if str(uid).isdigit() and isinstance(ids, list):
                favs[int(uid)] = {int(x) for x in ids if str(x).isdigit()}
    roles: dict[str, int] = {}
    raw_roles = data.get("wealth_roles", {})
    if isinstance(raw_roles, dict):
        for name, role_id in raw_roles.items():
            if str(role_id).isdigit():
                roles[str(name)] = int(role_id)
    return favs, roles


def tier_key_for_name(name: str) -> str | None:
    wanted = name.strip().lower()
    for tier in TIERS:
        if tier.name.lower() == wanted:
            return tier.key
    return None


@dataclass
class ImportReport:
    balances: int = 0
    coins: int = 0
    board: int = 0
    entrances: int = 0
    favorites: int = 0
    skipped: list[str] = field(default_factory=list)
    old_roles: dict[str, int] = field(default_factory=dict)  # tier key -> old role id

    def summary(self) -> str:
        text = (
            f"{self.balances} saldi ({self.coins} Marioncelli), {self.board} suoni della "
            f"soundboard, {self.entrances} suoni d'entrata, {self.favorites} preferiti"
        )
        if self.skipped:
            text += f"; saltati {len(self.skipped)}"
        return text


class LegacyImporter:
    def __init__(
        self, pool: Pool, ledger: Ledger, board: SoundboardRepo, entrances: SoundsRepo
    ) -> None:
        self._pool = pool
        self._ledger = ledger
        self._board = board
        self._entrances = entrances

    async def _done(self, message_id: int, kind: str) -> str | None:
        """None if this message was not imported yet, else what it became ('' if nothing)."""
        value: str | None = await self._pool.fetchval(
            "select coalesce(target, '') from marione.legacy_imports"
            " where message_id = $1 and kind = $2",
            message_id,
            kind,
        )
        return value

    async def _mark(self, message_id: int, kind: str, target: str | None) -> None:
        await self._pool.execute(
            "insert into marione.legacy_imports (message_id, kind, target) values ($1, $2, $3)"
            " on conflict do nothing",
            message_id,
            kind,
            target,
        )

    async def run(self, history: AsyncIterable[LegacyMessage]) -> ImportReport:
        report = ImportReport()
        economy: LegacyMessage | None = None
        settings: LegacyMessage | None = None
        board: list[tuple[LegacyMessage, BoardEntry]] = []
        entrances: list[tuple[LegacyMessage, int]] = []
        async for msg in history:  # oldest first: the last JSON seen is the newest
            if not msg.attachments:
                continue
            if msg.content.startswith("MARIONE_ECON"):
                economy = msg
            elif msg.content.startswith("MARIONE_SETTINGS"):
                settings = msg
            elif (entry := parse_board(msg.content)) is not None:
                board.append((msg, entry))
            elif (uid := parse_entrance(msg.content)) is not None:
                entrances.append((msg, uid))

        if economy is not None:
            await self._import_economy(economy, report)
        sound_ids: dict[int, int] = {}
        for msg, entry in board:
            new_id = await self._import_board(msg, entry, report)
            if new_id:
                sound_ids[msg.id] = new_id
        for msg, uid in entrances:
            await self._import_entrance(msg, uid, report)
        if settings is not None:
            await self._import_settings(settings, sound_ids, report)
        logger.info("Legacy import: %s", report.summary())
        return report

    async def _json(self, msg: LegacyMessage) -> Any:
        try:
            return json.loads((await msg.attachments[0].read()).decode())
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("unreadable legacy JSON in message %s: %s", msg.id, exc)
            return None

    async def _import_economy(self, msg: LegacyMessage, report: ImportReport) -> None:
        for uid, (balance, name) in sorted(parse_economy(await self._json(msg)).items()):
            if name:
                await self._ledger.remember_name(uid, name)
            if balance <= 0:
                continue
            # One key per member: the same old balance can never be credited twice.
            key = f"legacy:balance:{uid}"
            if await self._pool.fetchval(
                "select 1 from marione.ledger where idempotency_key = $1", key
            ):
                continue
            report.coins += await self._ledger.credit(uid, balance, "legacy_import", key=key)
            report.balances += 1

    async def _import_board(
        self, msg: LegacyMessage, entry: BoardEntry, report: ImportReport
    ) -> int | None:
        previous = await self._done(msg.id, "board")
        if previous is not None:
            return int(previous) if previous else None
        try:
            data = await msg.attachments[0].read()
            kind, duration = await audio.inspect(data, max_ms=LEGACY_BOARD_MAX_MS)
            new_id = await self._add_board(entry, kind, data, duration)
        except SoundError as exc:
            report.skipped.append(f"soundboard «{entry.name}»: {exc}")
            await self._mark(msg.id, "board", None)
            return None
        await self._mark(msg.id, "board", str(new_id))
        report.board += 1
        return new_id

    async def _add_board(self, entry: BoardEntry, kind: str, data: bytes, duration: int) -> int:
        name = entry.name
        for attempt in range(2, 10):
            try:
                return await self._board.add(
                    entry.creator,
                    name,
                    entry.emoji,
                    kind,
                    data,
                    duration,
                    max_duration_ms=LEGACY_BOARD_MAX_MS,
                )
            except SoundError as exc:
                if "already exists" not in str(exc):
                    raise
                name = f"{entry.name[:36]} {attempt}"
        raise SoundError("too many sounds with this name")

    async def _import_entrance(self, msg: LegacyMessage, uid: int, report: ImportReport) -> None:
        if await self._done(msg.id, "entrance") is not None:
            return
        attachment = msg.attachments[0]
        base = entrance_name(attachment.filename, uid)
        try:
            data = await attachment.read()
            kind, duration = await audio.inspect(data, max_ms=LEGACY_ENTRANCE_MAX_MS)
            name = base
            for attempt in range(2, 10):
                try:
                    await self._entrances.add(uid, name, kind, data, duration)
                    break
                except SoundError as exc:
                    if "already" not in str(exc):
                        raise
                    name = f"{base[:56]} {attempt}"
        except SoundError as exc:
            report.skipped.append(f"entrata «{base}» di {uid}: {exc}")
            await self._mark(msg.id, "entrance", None)
            return
        await self._mark(msg.id, "entrance", name)
        report.entrances += 1

    async def _import_settings(
        self, msg: LegacyMessage, sound_ids: dict[int, int], report: ImportReport
    ) -> None:
        favs, roles = parse_settings(await self._json(msg))
        for uid, old_ids in favs.items():
            for old in old_ids:
                new_id = sound_ids.get(old)
                if new_id is None:
                    stored = await self._done(old, "board")
                    new_id = int(stored) if stored else None
                if new_id is not None:
                    await self._board.add_favorite(uid, new_id)
                    report.favorites += 1
        for name, role_id in roles.items():
            key = tier_key_for_name(name)
            if key is not None:
                report.old_roles[key] = role_id
