"""The games API: the lobby, tables and moves (contract in docs/WEB_API.md, "Giochi").

The page polls `GET /api/games/table` with the version it has: the answer comes back as soon as
something changes (or after ~25 s), so moves of other players and bots appear at once.
"""

from typing import Any

from aiohttp import web

from marione.games.registry import GAMES
from marione.games.tables import GameHall, TableError
from marione.i18n import t
from marione.web.api import Who, _auth, _deps, _feature_off, _int, _json, fail

STATUS = {
    "not_found": 404,
    "forbidden": 403,
    "unknown_game": 400,
    "unknown_mode": 400,
    "bad_stake": 400,
    "illegal": 409,
    "not_your_turn": 409,
    "not_playing": 409,
    "already_started": 409,
    "table_full": 409,
    "seat_taken": 409,
    "not_a_bot": 409,
    "insufficient_funds": 409,
    "too_many_tables": 429,
    "too_many_yours": 429,
}


def _hall(request: web.Request) -> GameHall:
    hall = _deps(request).games
    if hall is None:
        raise web.HTTPServiceUnavailable()
    return hall


def _error(exc: TableError, who: Who) -> web.Response:
    extra = {k: v for k, v in exc.extra.items() if k != "detail"}
    return fail(STATUS.get(exc.code, 400), exc.code, t("game." + exc.code, who.lang), **extra)


async def _guard(request: web.Request) -> tuple[Who, web.Response | None]:
    who, err = await _auth(request)
    if err:
        return who, err
    if off := await _feature_off(request, who, "economy", "games"):
        return who, off
    return who, None


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "economy": cls.economy,
            "house": cls.house,
            "modes": [
                {"key": m.key, "seats": m.seats, "teams": [list(x) for x in m.teams]}
                for m in cls.modes
            ],
        }
        for key, cls in GAMES.items()
    ]


async def lobby(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    hall = _hall(request)
    svc = _deps(request).services
    mine = str(who.id)
    tables = [
        hall.summary(tb) for tb in hall.lobby() if tb.status == "waiting" or who.id in tb.humans
    ]
    return web.json_response(
        {
            "ok": True,
            "games": catalog(),
            "tables": tables,
            "you": mine,
            "stats": await svc.games.stats(who.id),
            "top": [
                {"userId": str(uid), "name": name, "net": net}
                for uid, name, net in await svc.games.top_winners()
            ],
            "enabled": await svc.settings.is_enabled("games"),
        }
    )


async def create(request: web.Request) -> web.Response:
    who, err = await _guard(request)
    if err:
        return err
    body = await _json(request)
    options: dict[str, Any] = {}
    raw = body.get("options")
    if isinstance(raw, dict):
        for key in ("level", "target", "hands"):  # the only options a page may set
            value = _int(raw.get(key))
            if value is not None:
                options[key] = value
    try:
        table = await _hall(request).create(
            who.id,
            who.member.name,
            str(body.get("game", "")),
            str(body.get("mode", "")),
            _int(body.get("stake")) or 0,
            bots=bool(body.get("bots")),
            options=options,
        )
    except TableError as exc:
        return _error(exc, who)
    return web.json_response({"ok": True, "table": _hall(request).view(table, who.id)})


async def _table_action(request: web.Request, name: str) -> web.Response:
    who, err = await _guard(request)
    if err:
        return err
    body = await _json(request)
    table_id = str(body.get("tableId", ""))
    hall = _hall(request)
    try:
        if name == "join":
            table = await hall.join(who.id, who.member.name, table_id, _int(body.get("seat")))
        elif name == "leave":
            await hall.leave(who.id, table_id)
            return web.json_response({"ok": True})
        elif name == "bot":
            await hall.add_bot(who.id, table_id)
            table = hall.get(table_id)
        elif name == "kick":
            await hall.kick_bot(who.id, table_id, _int(body.get("seat")) or 0)
            table = hall.get(table_id)
        elif name == "start":
            table = await hall.start(who.id, table_id)
        else:
            action = body.get("action")
            if not isinstance(action, dict):
                return fail(400, "illegal", t("game.illegal", who.lang))
            table = await hall.act(who.id, table_id, action)
    except TableError as exc:
        return _error(exc, who)
    return web.json_response({"ok": True, "table": hall.view(table, who.id)})


async def join(request: web.Request) -> web.Response:
    return await _table_action(request, "join")


async def leave(request: web.Request) -> web.Response:
    return await _table_action(request, "leave")


async def add_bot(request: web.Request) -> web.Response:
    return await _table_action(request, "bot")


async def kick_bot(request: web.Request) -> web.Response:
    return await _table_action(request, "kick")


async def start(request: web.Request) -> web.Response:
    return await _table_action(request, "start")


async def act(request: web.Request) -> web.Response:
    return await _table_action(request, "act")


async def table_state(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    hall = _hall(request)
    version = _int(request.query.get("v"))
    try:
        if version is None:
            table = hall.get(request.query.get("id", ""))
        else:
            table = await hall.wait(request.query.get("id", ""), version, 25.0)
    except TableError as exc:
        return _error(exc, who)
    return web.json_response({"ok": True, "table": hall.view(table, who.id)})


def add_routes(app: web.Application) -> None:
    r = app.router
    r.add_get("/api/games", lobby)
    r.add_get("/api/games/table", table_state)
    r.add_post("/api/games/create", create)
    r.add_post("/api/games/join", join)
    r.add_post("/api/games/leave", leave)
    r.add_post("/api/games/bot", add_bot)
    r.add_post("/api/games/kick", kick_bot)
    r.add_post("/api/games/start", start)
    r.add_post("/api/games/act", act)
