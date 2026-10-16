"""The JSON API and the Discord login (the contract is docs/WEB_API.md)."""

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import web
from aiohttp.web_request import FileField

from marione.bot.adapters import unit
from marione.bot.texts import rob_line, rob_refusal
from marione.db.settings import FEATURES
from marione.db.sounds import MAX_BYTES, SoundError
from marione.llm.budget import period_starts
from marione.ports import GuildMember, PlayOutcome
from marione.web import oauth, session
from marione.web.deps import WebDeps
from marione.web.view import build_state, member_json, sounds_json

DEPS = web.AppKey("deps", WebDeps)
MAX_MONEY = 10_000_000_000
# How a refused heist is reported: status -> (HTTP status, error code)
REFUSALS = {
    "cooldown": (429, "cooldown"),
    "victim_poor": (409, "insufficient"),
    "broke": (409, "insufficient"),
}


def fail(status: int, code: str, message: str, **extra: Any) -> web.Response:
    return web.json_response(
        {"ok": False, "error": code, "message": message, **extra}, status=status
    )


def plain(text: str) -> str:
    return text.replace("**", "")


def _deps(request: web.Request) -> WebDeps:
    return request.app[DEPS]


def _uid(request: web.Request) -> int | None:
    deps = _deps(request)
    if deps.dev_user_id is not None:
        return deps.dev_user_id
    data = session.loads(
        request.cookies.get(session.COOKIE_NAME, ""), deps.services.config.web_session_secret
    )
    try:
        return int(data["uid"])
    except (KeyError, TypeError, ValueError):
        return None


async def _auth(
    request: web.Request, *, admin: bool = False
) -> tuple[GuildMember, web.Response | None]:
    """The signed-in server member, or the error response to send."""
    uid = _uid(request)
    placeholder = GuildMember(0, "", "", None, False, None)
    if uid is None:
        return placeholder, fail(401, "unauthorized", "Accedi con Discord.")
    member = _deps(request).guild.member(uid)
    if member is None:
        return placeholder, fail(403, "not_in_guild", "Non sei nel server.")
    if admin and not member.is_admin:
        return placeholder, fail(403, "forbidden", "Serve essere amministratore.")
    return member, None


def _limited(request: web.Request, member: GuildMember) -> web.Response | None:
    if _deps(request).limiter.allow(member.id, time.monotonic()):
        return None
    return fail(429, "cooldown", "Troppe richieste: aspetta un attimo.", cooldownSeconds=10)


async def _json(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _feature_off(request: web.Request, *keys: str) -> web.Response | None:
    settings = _deps(request).services.settings
    for key in keys:
        if not await settings.is_enabled(key):
            return fail(409, "feature_off", "Questa funzione è spenta al momento.")
    return None


# --- login ---------------------------------------------------------------------------------------


async def me(request: web.Request) -> web.Response:
    cfg = _deps(request).services.config
    dev = _deps(request).dev_user_id is not None
    if not (cfg.oauth_ready or dev):
        return web.json_response({"configured": False, "loggedIn": False})
    uid = _uid(request)
    if uid is None:
        return web.json_response({"configured": True, "loggedIn": False})
    member = _deps(request).guild.member(uid)
    if member is None:
        return web.json_response({"configured": True, "loggedIn": True, "inGuild": False})
    return web.json_response(
        {
            "configured": True,
            "loggedIn": True,
            "inGuild": True,
            **member_json(member),
            "isAdmin": member.is_admin,
            "inVoice": member.voice_channel is not None,
            "voiceChannel": member.voice_channel,
        }
    )


def _redirect_uri(request: web.Request) -> str:
    return _deps(request).services.config.public_url.rstrip("/") + "/auth/callback"


def _secure(request: web.Request) -> bool:
    return _deps(request).services.config.public_url.startswith("https://")


async def auth_login(request: web.Request) -> web.Response:
    deps = _deps(request)
    cfg = deps.services.config
    if deps.dev_user_id is not None:
        raise web.HTTPFound("/")
    if not cfg.oauth_ready:
        return web.Response(text="Il login non è configurato.", status=503)
    state = secrets.token_urlsafe(16)
    response = web.HTTPFound(
        oauth.authorize_url(cfg.discord_client_id, _redirect_uri(request), state)
    )
    response.set_cookie(
        "marione_state", state, max_age=600, httponly=True, samesite="Lax", secure=_secure(request)
    )
    raise response


async def auth_callback(request: web.Request) -> web.Response:
    deps = _deps(request)
    cfg = deps.services.config
    if not cfg.oauth_ready:
        return web.Response(text="Il login non è configurato.", status=503)
    code, state = request.query.get("code"), request.query.get("state")
    expected = request.cookies.get("marione_state")
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        return web.Response(text="Accesso fallito (stato non valido). Riprova.", status=400)
    token = await oauth.exchange_code(
        deps.http, cfg.discord_client_id, cfg.discord_client_secret, _redirect_uri(request), code
    )
    user = await oauth.fetch_user(deps.http, token["access_token"]) if token else None
    if not user or "id" not in user:
        return web.Response(text="Accesso fallito. Riprova.", status=502)
    response = web.HTTPFound("/")
    response.set_cookie(
        session.COOKIE_NAME,
        session.dumps({"uid": str(user["id"])}, cfg.web_session_secret),
        max_age=session.MAX_AGE_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=_secure(request),
        path="/",
    )
    response.del_cookie("marione_state")
    raise response


async def auth_logout(request: web.Request) -> web.Response:
    response = web.HTTPFound("/")
    response.del_cookie(session.COOKIE_NAME, path="/")
    raise response


# --- state ---------------------------------------------------------------------------------------


async def state(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    return web.json_response(await build_state(_deps(request), member))


async def live(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    svc = _deps(request).services
    return web.json_response(
        {
            "ok": True,
            "balance": await svc.ledger.balance(member.id),
            "inVoice": member.voice_channel is not None,
            "voiceChannel": member.voice_channel,
            "robCooldownSeconds": await svc.economy.rob_cooldown(member.id),
        }
    )


# --- economy -------------------------------------------------------------------------------------


async def pay(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, member):
        return limited
    if off := await _feature_off(request, "economy"):
        return off
    body = await _json(request)
    target, amount = _int(body.get("memberId")), _int(body.get("amount"))
    if target is None or amount is None or not 0 < amount <= MAX_MONEY:
        return fail(400, "bad_request", "Scegli un membro e un importo valido.")
    receiver = _deps(request).guild.member(target)
    if receiver is None or target == member.id:
        return fail(400, "bad_request", "Non puoi mandarli a questo membro.")
    svc = _deps(request).services
    await svc.ledger.remember_name(member.id, member.name)
    await svc.ledger.remember_name(receiver.id, receiver.name)
    ok = await svc.economy.pay(
        member.id, receiver.id, amount, key=f"webpay:{member.id}:{secrets.token_hex(8)}"
    )
    if not ok:
        return fail(409, "insufficient", "Non hai abbastanza Marioncelli.")
    return web.json_response(
        {
            "ok": True,
            "balance": await svc.ledger.balance(member.id),
            "message": f"Hai mandato {amount} {unit(amount)} a {receiver.name}.",
        }
    )


async def rob_preview(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    if off := await _feature_off(request, "economy", "rob"):
        return off
    victim, amount = _int(request.query.get("victimId")), _int(request.query.get("amount"))
    if victim is None or amount is None or amount < 0 or victim == member.id:
        return fail(400, "bad_request", "Scegli una vittima e un importo.")
    if _deps(request).guild.member(victim) is None:
        return fail(400, "bad_request", "Vittima non trovata.")
    svc = _deps(request).services
    odds = await svc.economy.rob_preview(member.id, victim, amount)
    return web.json_response(
        {
            "ok": True,
            "prob": odds.probability,
            "fine": odds.fine,
            "cooldownSeconds": await svc.economy.rob_cooldown(member.id),
        }
    )


async def rob(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, member):
        return limited
    if off := await _feature_off(request, "economy", "rob"):
        return off
    body = await _json(request)
    victim_id, amount = _int(body.get("victimId")), _int(body.get("amount"))
    if victim_id is None or amount is None or amount <= 0 or amount > MAX_MONEY:
        return fail(400, "bad_request", "Scegli una vittima e un importo valido.")
    victim = _deps(request).guild.member(victim_id)
    if victim is None:
        return fail(400, "bad_request", "Vittima non trovata.")
    svc = _deps(request).services
    await svc.ledger.remember_name(member.id, member.name)
    await svc.ledger.remember_name(victim.id, victim.name)
    result = await svc.economy.rob(member.id, victim.id, amount)
    if result.refused:
        message = rob_refusal(result, svc.economy_rules.robbery.min_amount)
        status, code = REFUSALS.get(result.status, (400, "bad_request"))
        return fail(status, code, message, cooldownSeconds=result.wait_seconds)
    line = rob_line(member.name, victim.name, result)
    await _deps(request).guild.announce(line)
    return web.json_response(
        {
            "ok": True,
            "success": result.status == "ok",
            "amount": result.amount,
            "fine": result.fine,
            "balance": await svc.ledger.balance(member.id),
            "cooldownSeconds": await svc.economy.rob_cooldown(member.id),
            "message": plain(line),
        }
    )


# --- soundboard ----------------------------------------------------------------------------------


async def board_list(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    deps = _deps(request)
    return web.json_response(
        {
            "ok": True,
            "sounds": await sounds_json(deps, member.id),
            "volume": await deps.services.settings.soundboard_volume(),
        }
    )


def _audio_response(content_type: str, data: bytes) -> web.Response:
    return web.Response(
        body=data,
        content_type=content_type,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


async def board_audio(request: web.Request) -> web.Response:
    _, err = await _auth(request)
    if err:
        return err
    sound_id = _int(request.query.get("id"))
    audio = await _deps(request).services.soundboard.audio(sound_id) if sound_id else None
    if audio is None:
        return fail(404, "not_found", "Suono non trovato.")
    return _audio_response(audio.content_type, audio.data)


async def board_play(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, member):
        return limited
    if off := await _feature_off(request, "soundboard"):
        return off
    sound_id = _int((await _json(request)).get("id"))
    svc = _deps(request).services
    audio = await svc.soundboard.audio(sound_id) if sound_id else None
    if audio is None:
        return fail(404, "not_found", "Suono non trovato.")
    outcome = await _deps(request).guild.play_for(
        member.id, audio.data, await svc.settings.soundboard_volume()
    )
    if outcome == PlayOutcome.NOT_IN_VOICE:
        return fail(409, "not_in_voice", "Entra prima in un canale vocale 🎧")
    if outcome == PlayOutcome.BUSY:
        return fail(409, "busy", "Sto già suonando in un altro canale.")
    if outcome != PlayOutcome.OK:
        return fail(502, "error", "Non riesco a suonare adesso, riprova.")
    return web.json_response({"ok": True})


async def board_stop(request: web.Request) -> web.Response:
    _, err = await _auth(request)
    if err:
        return err
    _deps(request).guild.stop_audio()
    return web.json_response({"ok": True})


async def board_volume(request: web.Request) -> web.Response:
    _, err = await _auth(request)
    if err:
        return err
    percent = _int((await _json(request)).get("percent"))
    if percent is None:
        return fail(400, "bad_request", "Volume non valido.")
    volume = await _deps(request).services.settings.set_soundboard_volume(percent)
    return web.json_response({"ok": True, "volume": volume})


async def board_favorite(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    sound_id = _int((await _json(request)).get("id"))
    fav = (
        await _deps(request).services.soundboard.toggle_favorite(member.id, sound_id)
        if sound_id
        else None
    )
    if fav is None:
        return fail(404, "not_found", "Suono non trovato.")
    return web.json_response({"ok": True, "fav": fav})


async def _read_upload(request: web.Request) -> tuple[dict[str, str], bytes | None]:
    form = await request.post()
    fields = {k: v for k, v in form.items() if isinstance(v, str)}
    upload = form.get("file")
    data = None
    if isinstance(upload, FileField):
        data = upload.file.read(MAX_BYTES + 1)
    return fields, data


def _sound_error(exc: SoundError) -> web.Response:
    text = str(exc)
    if "already" in text:
        return fail(409, "exists", "Esiste già un suono con questo nome.")
    if ("at most" in text and "sounds" in text) or "full" in text:
        return fail(409, "limit", "Hai raggiunto il limite di suoni.")
    if "8 MB" in text:
        return fail(413, "too_large", "Il file è troppo grande (max 8 MB).")
    return fail(422, "invalid_audio", "Audio non valido: usa mp3, wav o ogg brevi.")


async def board_add(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, member):
        return limited
    fields, data = await _read_upload(request)
    if not data:
        return fail(400, "bad_request", "Manca il file audio.")
    if len(data) > MAX_BYTES:
        return fail(413, "too_large", "Il file è troppo grande (max 8 MB).")
    svc = _deps(request).services
    await svc.ledger.remember_name(member.id, member.name)
    try:
        sound_id = await svc.sound_service.add_to_board(
            member.id, fields.get("name", ""), fields.get("emoji", ""), data
        )
    except SoundError as exc:
        return _sound_error(exc)
    sound = await svc.soundboard.get(sound_id)
    assert sound is not None
    return web.json_response(
        {
            "ok": True,
            "sound": {
                "id": str(sound.id),
                "name": sound.name,
                "emoji": sound.emoji,
                "durationMs": sound.duration_ms,
                "fav": False,
                "own": True,
            },
        }
    )


async def _own_sound(
    request: web.Request, member: GuildMember
) -> tuple[int, dict[str, Any], web.Response | None]:
    """The sound a request wants to change, if this member may change it."""
    body = await _json(request)
    sound_id = _int(body.get("id"))
    svc = _deps(request).services
    sound = await svc.soundboard.get(sound_id) if sound_id else None
    if sound is None:
        return 0, body, fail(404, "not_found", "Suono non trovato.")
    if not svc.sound_service.may_modify(sound, member.id, is_admin=member.is_admin):
        return 0, body, fail(403, "forbidden", "Puoi modificare solo i tuoi suoni.")
    return sound.id, body, None


async def board_rename(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    sound_id, body, err = await _own_sound(request, member)
    if err:
        return err
    emoji = body.get("emoji")
    try:
        await _deps(request).services.soundboard.rename(
            sound_id, str(body.get("name", "")), emoji if isinstance(emoji, str) else None
        )
    except SoundError as exc:
        return _sound_error(exc)
    return web.json_response({"ok": True})


async def board_remove(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    sound_id, _, err = await _own_sound(request, member)
    if err:
        return err
    await _deps(request).services.soundboard.remove(sound_id)
    return web.json_response({"ok": True})


# --- entrance sounds -----------------------------------------------------------------------------


async def entrance_list(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    from marione.db.sounds import MAX_PER_MEMBER

    items = await _deps(request).services.sounds.list(member.id)
    return web.json_response(
        {
            "ok": True,
            "entrances": [
                {"name": s.name, "size": s.size, "durationMs": s.duration_ms} for s in items
            ],
            "limit": MAX_PER_MEMBER,
        }
    )


async def entrance_audio(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    sound = await _deps(request).services.sounds.get(member.id, request.query.get("name", ""))
    if sound is None:
        return fail(404, "not_found", "Suono non trovato.")
    return _audio_response(sound.content_type, sound.data)


async def entrance_add(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, member):
        return limited
    fields, data = await _read_upload(request)
    if not data:
        return fail(400, "bad_request", "Manca il file audio.")
    if len(data) > MAX_BYTES:
        return fail(413, "too_large", "Il file è troppo grande (max 8 MB).")
    svc = _deps(request).services
    await svc.ledger.remember_name(member.id, member.name)
    try:
        await svc.sound_service.add_entrance(member.id, fields.get("name", ""), data)
    except SoundError as exc:
        return _sound_error(exc)
    return web.json_response({"ok": True})


async def entrance_remove(request: web.Request) -> web.Response:
    member, err = await _auth(request)
    if err:
        return err
    name = str((await _json(request)).get("name", ""))
    removed = await _deps(request).services.sounds.remove(member.id, name)
    if not removed:
        return fail(404, "not_found", "Suono non trovato.")
    return web.json_response({"ok": True})


# --- administrators ------------------------------------------------------------------------------


async def admin_balance(request: web.Request) -> web.Response:
    admin, err = await _auth(request, admin=True)
    if err:
        return err
    body = await _json(request)
    target, amount = _int(body.get("memberId")), _int(body.get("amount"))
    action = body.get("action")
    if target is None or amount is None or not 0 <= amount <= MAX_MONEY:
        return fail(400, "bad_request", "Membro o importo non validi.")
    if action not in ("give", "take", "set") or (action != "set" and amount == 0):
        return fail(400, "bad_request", "Azione non valida.")
    member = _deps(request).guild.member(target)
    if member is None:
        return fail(404, "not_found", "Membro non trovato.")
    ledger = _deps(request).services.ledger
    await ledger.remember_name(member.id, member.name)
    current = await ledger.balance(member.id)
    wanted = {"give": current + amount, "take": max(0, current - amount), "set": amount}[action]
    await ledger.set_balance(member.id, wanted, admin_id=admin.id)
    return web.json_response({"ok": True, "balance": await ledger.balance(member.id)})


async def admin_feature(request: web.Request) -> web.Response:
    _, err = await _auth(request, admin=True)
    if err:
        return err
    body = await _json(request)
    key, on = body.get("key"), body.get("on")
    if key not in FEATURES or not isinstance(on, bool):
        return fail(400, "bad_request", "Funzione non valida.")
    settings = _deps(request).services.settings
    await settings.set_enabled(key, on)
    return web.json_response({"ok": True, "modules": await settings.flags()})


async def admin_usage(request: web.Request) -> web.Response:
    _, err = await _auth(request, admin=True)
    if err:
        return err
    svc = _deps(request).services
    cfg = svc.config
    now = datetime.now(UTC)
    day, month = period_starts(now, ZoneInfo(cfg.timezone))
    by_model = await svc.usage.by_model_since(now - timedelta(days=7))
    return web.json_response(
        {
            "ok": True,
            "aiEnabled": svc.llm is not None,
            "todayUsd": float(await svc.usage.spent_since(day)),
            "monthUsd": float(await svc.usage.spent_since(month)),
            "dailyBudgetUsd": cfg.agent_daily_budget_usd,
            "monthlyBudgetUsd": cfg.agent_monthly_budget_usd,
            "byModel": [{"model": m, "calls": n, "costUsd": float(c)} for m, n, c in by_model],
        }
    )


def add_routes(app: web.Application) -> None:
    r = app.router
    r.add_get("/api/me", me)
    r.add_get("/auth/login", auth_login)
    r.add_get("/auth/callback", auth_callback)
    r.add_get("/auth/logout", auth_logout)
    r.add_post("/auth/logout", auth_logout)
    r.add_get("/api/state", state)
    r.add_get("/api/live", live)
    r.add_post("/api/economy/pay", pay)
    r.add_get("/api/economy/rob-preview", rob_preview)
    r.add_post("/api/economy/rob", rob)
    r.add_get("/api/soundboard/list", board_list)
    r.add_get("/api/soundboard/audio", board_audio)
    r.add_post("/api/soundboard/play", board_play)
    r.add_post("/api/soundboard/stop", board_stop)
    r.add_post("/api/soundboard/volume", board_volume)
    r.add_post("/api/soundboard/favorite", board_favorite)
    r.add_post("/api/soundboard/add", board_add)
    r.add_post("/api/soundboard/rename", board_rename)
    r.add_post("/api/soundboard/remove", board_remove)
    r.add_get("/api/entrance/list", entrance_list)
    r.add_get("/api/entrance/audio", entrance_audio)
    r.add_post("/api/entrance/add", entrance_add)
    r.add_post("/api/entrance/remove", entrance_remove)
    r.add_post("/api/admin/balance", admin_balance)
    r.add_post("/api/admin/feature", admin_feature)
    r.add_get("/api/admin/usage", admin_usage)
