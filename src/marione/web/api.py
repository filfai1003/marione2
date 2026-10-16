"""The JSON API and the Discord login (the contract is docs/WEB_API.md).

Every text sent back is in the visitor's language (see `marione.i18n`).
"""

import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import web
from aiohttp.web_request import FileField

from marione.agent import persona
from marione.agent import prompt as prompts
from marione.bot.texts import rob_line, rob_refusal
from marione.db.settings import FEATURES
from marione.db.sounds import MAX_BYTES, MAX_PER_MEMBER, SoundError
from marione.i18n import LANGS, normalize, t, unit
from marione.llm.budget import period_starts
from marione.ports import GuildMember, PlayOutcome
from marione.web import oauth, session
from marione.web.deps import WebDeps
from marione.web.view import build_state, history, iso, leaderboard, member_json, sounds_json

DEPS = web.AppKey("deps", WebDeps)
MAX_MONEY = 10_000_000_000
# How a refused heist is reported: status -> (HTTP status, error code)
REFUSALS = {
    "cooldown": (429, "cooldown"),
    "victim_poor": (409, "insufficient"),
    "broke": (409, "insufficient"),
}


@dataclass(frozen=True)
class Who:
    member: GuildMember
    lang: str

    @property
    def id(self) -> int:
        return self.member.id


def fail(status: int, code: str, message: str, **extra: Any) -> web.Response:
    return web.json_response(
        {"ok": False, "error": code, "message": message, **extra}, status=status
    )


def plain(text: str) -> str:
    return text.replace("**", "")


def _deps(request: web.Request) -> WebDeps:
    return request.app[DEPS]


def browser_lang(request: web.Request) -> str:
    for part in request.headers.get("Accept-Language", "").split(","):
        code = normalize(part.split(";")[0])
        if code:
            return code
    return "en"


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


async def _lang(request: web.Request, uid: int | None) -> str:
    settings = _deps(request).services.settings
    if uid is not None and (chosen := await settings.user_language(uid)):
        return chosen
    return await settings.server_language()


async def _auth(request: web.Request, *, admin: bool = False) -> tuple[Who, web.Response | None]:
    """The signed-in server member and their language, or the error response to send."""
    uid = _uid(request)
    nobody = Who(GuildMember(0, "", "", None, False, None), browser_lang(request))
    if uid is None:
        return nobody, fail(401, "unauthorized", t("login_required", nobody.lang))
    member = _deps(request).guild.member(uid)
    lang = await _lang(request, uid)
    if member is None:
        return nobody, fail(403, "not_in_guild", t("not_in_guild", lang))
    if admin and not member.is_admin:
        return nobody, fail(403, "forbidden", t("admin_only", lang))
    return Who(member, lang), None


def _limited(request: web.Request, who: Who) -> web.Response | None:
    if _deps(request).limiter.allow(who.id, time.monotonic()):
        return None
    return fail(429, "cooldown", t("too_many", who.lang), cooldownSeconds=10)


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


def _page(request: web.Request, default: int = 10) -> tuple[int, int]:
    offset = max(0, _int(request.query.get("offset")) or 0)
    limit = _int(request.query.get("limit")) or default
    return offset, max(1, min(50, limit))


async def _feature_off(request: web.Request, who: Who, *keys: str) -> web.Response | None:
    settings = _deps(request).services.settings
    for key in keys:
        if not await settings.is_enabled(key):
            return fail(409, "feature_off", t("feature_off", who.lang))
    return None


# --- login and language --------------------------------------------------------------------------


async def me(request: web.Request) -> web.Response:
    deps = _deps(request)
    cfg = deps.services.config
    uid = _uid(request)
    lang = await _lang(request, uid) if uid is not None else browser_lang(request)
    base = {"lang": lang, "languages": list(LANGS)}
    if not (cfg.oauth_ready or deps.dev_user_id is not None):
        return web.json_response({"configured": False, "loggedIn": False, **base})
    if uid is None:
        return web.json_response({"configured": True, "loggedIn": False, **base})
    member = deps.guild.member(uid)
    if member is None:
        return web.json_response({"configured": True, "loggedIn": True, "inGuild": False, **base})
    return web.json_response(
        {
            "configured": True,
            "loggedIn": True,
            "inGuild": True,
            **member_json(member),
            "isAdmin": member.is_admin,
            "inVoice": member.voice_channel is not None,
            "voiceChannel": member.voice_channel,
            **base,
        }
    )


async def set_language(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    code = normalize(str((await _json(request)).get("lang", "")))
    if code is None:
        return fail(400, "bad_request", t("bad_request", who.lang))
    await _deps(request).services.settings.set_user_language(who.id, code)
    return web.json_response({"ok": True, "lang": code})


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
        return web.Response(text="Login is not configured.", status=503)
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
        return web.Response(text="Login is not configured.", status=503)
    code, state = request.query.get("code"), request.query.get("state")
    expected = request.cookies.get("marione_state")
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        return web.Response(text="Login failed (invalid state). Please try again.", status=400)
    token = await oauth.exchange_code(
        deps.http, cfg.discord_client_id, cfg.discord_client_secret, _redirect_uri(request), code
    )
    user = await oauth.fetch_user(deps.http, token["access_token"]) if token else None
    if not user or "id" not in user:
        return web.Response(text="Login failed. Please try again.", status=502)
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
    who, err = await _auth(request)
    if err:
        return err
    return web.json_response(await build_state(_deps(request), who.member, who.lang))


async def live(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    svc = _deps(request).services
    return web.json_response(
        {
            "ok": True,
            "balance": await svc.ledger.balance(who.id),
            "inVoice": who.member.voice_channel is not None,
            "voiceChannel": who.member.voice_channel,
            "robCooldownSeconds": await svc.economy.rob_cooldown(who.id),
        }
    )


# --- economy -------------------------------------------------------------------------------------


async def leaderboard_page(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    offset, limit = _page(request)
    total, items = await leaderboard(
        _deps(request), who.id, request.query.get("q", "")[:60], offset, limit
    )
    return web.json_response({"ok": True, "total": total, "items": items})


async def history_page(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    offset, limit = _page(request)
    total, items = await history(_deps(request), who.id, who.lang, offset, limit)
    return web.json_response({"ok": True, "total": total, "items": items})


async def pay(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, who):
        return limited
    if off := await _feature_off(request, who, "economy"):
        return off
    body = await _json(request)
    target, amount = _int(body.get("memberId")), _int(body.get("amount"))
    if target is None or amount is None or not 0 < amount <= MAX_MONEY:
        return fail(400, "bad_request", t("pay_invalid", who.lang))
    receiver = _deps(request).guild.member(target)
    if receiver is None or target == who.id:
        return fail(400, "bad_request", t("pay_bad_target", who.lang))
    svc = _deps(request).services
    await svc.ledger.remember_name(who.id, who.member.name)
    await svc.ledger.remember_name(receiver.id, receiver.name)
    ok = await svc.economy.pay(
        who.id, receiver.id, amount, key=f"webpay:{who.id}:{secrets.token_hex(8)}"
    )
    if not ok:
        return fail(409, "insufficient", t("not_enough", who.lang))
    return web.json_response(
        {
            "ok": True,
            "balance": await svc.ledger.balance(who.id),
            "message": t("paid", who.lang, amount=amount, unit=unit(amount), name=receiver.name),
        }
    )


async def rob_preview(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    if off := await _feature_off(request, who, "economy", "rob"):
        return off
    victim, amount = _int(request.query.get("victimId")), _int(request.query.get("amount"))
    if victim is None or amount is None or amount < 0 or victim == who.id:
        return fail(400, "bad_request", t("rob_pick", who.lang))
    if _deps(request).guild.member(victim) is None:
        return fail(400, "bad_request", t("victim_not_found", who.lang))
    svc = _deps(request).services
    odds = await svc.economy.rob_preview(who.id, victim, amount)
    return web.json_response(
        {
            "ok": True,
            "prob": odds.probability,
            "fine": odds.fine,
            "cooldownSeconds": await svc.economy.rob_cooldown(who.id),
        }
    )


async def rob(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, who):
        return limited
    if off := await _feature_off(request, who, "economy", "rob"):
        return off
    body = await _json(request)
    victim_id, amount = _int(body.get("victimId")), _int(body.get("amount"))
    if victim_id is None or amount is None or amount <= 0 or amount > MAX_MONEY:
        return fail(400, "bad_request", t("rob_pick", who.lang))
    victim = _deps(request).guild.member(victim_id)
    if victim is None:
        return fail(400, "bad_request", t("victim_not_found", who.lang))
    svc = _deps(request).services
    await svc.ledger.remember_name(who.id, who.member.name)
    await svc.ledger.remember_name(victim.id, victim.name)
    result = await svc.economy.rob(who.id, victim.id, amount)
    if result.refused:
        message = rob_refusal(result, svc.economy_rules.robbery.min_amount, who.lang)
        status, code = REFUSALS.get(result.status, (400, "bad_request"))
        return fail(status, code, message, cooldownSeconds=result.wait_seconds)
    server_lang = await svc.settings.server_language()
    await _deps(request).guild.announce(rob_line(who.member.name, victim.name, result, server_lang))
    return web.json_response(
        {
            "ok": True,
            "success": result.status == "ok",
            "amount": result.amount,
            "fine": result.fine,
            "balance": await svc.ledger.balance(who.id),
            "cooldownSeconds": await svc.economy.rob_cooldown(who.id),
            "message": plain(rob_line(who.member.name, victim.name, result, who.lang)),
        }
    )


# --- soundboard ----------------------------------------------------------------------------------


async def board_list(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    deps = _deps(request)
    return web.json_response(
        {
            "ok": True,
            "sounds": await sounds_json(deps, who.id),
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
    who, err = await _auth(request)
    if err:
        return err
    sound_id = _int(request.query.get("id"))
    audio = await _deps(request).services.soundboard.audio(sound_id) if sound_id else None
    if audio is None:
        return fail(404, "not_found", t("sound_not_found", who.lang))
    return _audio_response(audio.content_type, audio.data)


async def board_play(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, who):
        return limited
    if off := await _feature_off(request, who, "soundboard"):
        return off
    sound_id = _int((await _json(request)).get("id"))
    svc = _deps(request).services
    audio = await svc.soundboard.audio(sound_id) if sound_id else None
    if audio is None:
        return fail(404, "not_found", t("sound_not_found", who.lang))
    outcome = await _deps(request).guild.play_for(
        who.id, audio.data, await svc.settings.soundboard_volume()
    )
    if outcome == PlayOutcome.NOT_IN_VOICE:
        return fail(409, "not_in_voice", t("not_in_voice", who.lang))
    if outcome == PlayOutcome.BUSY:
        return fail(409, "busy", t("busy", who.lang))
    if outcome != PlayOutcome.OK:
        return fail(502, "error", t("play_error", who.lang))
    return web.json_response({"ok": True})


async def board_stop(request: web.Request) -> web.Response:
    _, err = await _auth(request)
    if err:
        return err
    _deps(request).guild.stop_audio()
    return web.json_response({"ok": True})


async def board_volume(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    percent = _int((await _json(request)).get("percent"))
    if percent is None:
        return fail(400, "bad_request", t("volume_invalid", who.lang))
    volume = await _deps(request).services.settings.set_soundboard_volume(percent)
    return web.json_response({"ok": True, "volume": volume})


async def board_favorite(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    sound_id = _int((await _json(request)).get("id"))
    fav = (
        await _deps(request).services.soundboard.toggle_favorite(who.id, sound_id)
        if sound_id
        else None
    )
    if fav is None:
        return fail(404, "not_found", t("sound_not_found", who.lang))
    return web.json_response({"ok": True, "fav": fav})


async def _read_upload(request: web.Request) -> tuple[dict[str, str], bytes | None]:
    form = await request.post()
    fields = {k: v for k, v in form.items() if isinstance(v, str)}
    upload = form.get("file")
    data = None
    if isinstance(upload, FileField):
        data = upload.file.read(MAX_BYTES + 1)
    return fields, data


def _sound_error(exc: SoundError, lang: str) -> web.Response:
    text = str(exc)
    if "already" in text:
        return fail(409, "exists", t("sound_exists", lang))
    if ("at most" in text and "sounds" in text) or "full" in text:
        return fail(409, "limit", t("sound_limit", lang))
    if "8 MB" in text:
        return fail(413, "too_large", t("too_large", lang))
    return fail(422, "invalid_audio", t("invalid_audio", lang))


def _upload_problem(data: bytes | None, lang: str) -> web.Response | None:
    if not data:
        return fail(400, "bad_request", t("file_missing", lang))
    if len(data) > MAX_BYTES:
        return fail(413, "too_large", t("too_large", lang))
    return None


async def board_add(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    if limited := _limited(request, who):
        return limited
    fields, data = await _read_upload(request)
    if problem := _upload_problem(data, who.lang):
        return problem
    assert data is not None
    svc = _deps(request).services
    await svc.ledger.remember_name(who.id, who.member.name)
    try:
        sound_id = await svc.sound_service.add_to_board(
            who.id, fields.get("name", ""), fields.get("emoji", ""), data
        )
    except SoundError as exc:
        return _sound_error(exc, who.lang)
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


async def board_rename(request: web.Request) -> web.Response:
    who, err = await _auth(request)
    if err:
        return err
    body = await _json(request)
    sound_id = _int(body.get("id"))
    svc = _deps(request).services
    sound = await svc.soundboard.get(sound_id) if sound_id else None
    if sound is None:
        return fail(404, "not_found", t("sound_not_found", who.lang))
    if not svc.sound_service.may_modify(sound, who.id, is_admin=who.member.is_admin):
        return fail(403, "forbidden", t("own_sounds_only", who.lang))
    emoji = body.get("emoji")
    try:
        await svc.soundboard.rename(
            sound.id, str(body.get("name", "")), emoji if isinstance(emoji, str) else None
        )
    except SoundError as exc:
        return _sound_error(exc, who.lang)
    return web.json_response({"ok": True})


async def board_remove(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)  # only administrators delete from the soundboard
    if err:
        return err
    sound_id = _int((await _json(request)).get("id"))
    removed = await _deps(request).services.soundboard.remove(sound_id) if sound_id else False
    if not removed:
        return fail(404, "not_found", t("sound_not_found", who.lang))
    return web.json_response({"ok": True})


# --- entrance sounds (administrators only) -------------------------------------------------------


def _target(
    request: web.Request, who: Who, raw: Any
) -> tuple[GuildMember | None, web.Response | None]:
    uid = _int(raw)
    member = _deps(request).guild.member(uid) if uid is not None else None
    if member is None:
        return None, fail(404, "not_found", t("member_not_found", who.lang))
    return member, None


async def entrance_members(request: web.Request) -> web.Response:
    _, err = await _auth(request, admin=True)
    if err:
        return err
    deps = _deps(request)
    counts = await deps.services.sounds.counts()
    members = sorted(deps.guild.members(), key=lambda m: (-counts.get(m.id, 0), m.name.lower()))
    return web.json_response(
        {
            "ok": True,
            "members": [
                {
                    "id": str(m.id),
                    "name": m.name,
                    "avatar": m.avatar_url,
                    "count": counts.get(m.id, 0),
                }
                for m in members
            ],
            "limit": MAX_PER_MEMBER,
        }
    )


async def entrance_list(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    member, err = _target(request, who, request.query.get("memberId"))
    if err or member is None:
        return err or fail(404, "not_found", "")
    items = await _deps(request).services.sounds.list(member.id)
    return web.json_response(
        {
            "ok": True,
            "memberId": str(member.id),
            "entrances": [
                {"name": s.name, "size": s.size, "durationMs": s.duration_ms} for s in items
            ],
            "limit": MAX_PER_MEMBER,
        }
    )


async def entrance_audio(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    member, err = _target(request, who, request.query.get("memberId"))
    if err or member is None:
        return err or fail(404, "not_found", "")
    sound = await _deps(request).services.sounds.get(member.id, request.query.get("name", ""))
    if sound is None:
        return fail(404, "not_found", t("sound_not_found", who.lang))
    return _audio_response(sound.content_type, sound.data)


async def entrance_add(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    if limited := _limited(request, who):
        return limited
    fields, data = await _read_upload(request)
    member, err = _target(request, who, fields.get("memberId"))
    if err or member is None:
        return err or fail(404, "not_found", "")
    if problem := _upload_problem(data, who.lang):
        return problem
    assert data is not None
    svc = _deps(request).services
    await svc.ledger.remember_name(member.id, member.name)
    try:
        await svc.sound_service.add_entrance(member.id, fields.get("name", ""), data)
    except SoundError as exc:
        return _sound_error(exc, who.lang)
    return web.json_response({"ok": True})


async def entrance_remove(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    body = await _json(request)
    member, err = _target(request, who, body.get("memberId"))
    if err or member is None:
        return err or fail(404, "not_found", "")
    removed = await _deps(request).services.sounds.remove(member.id, str(body.get("name", "")))
    if not removed:
        return fail(404, "not_found", t("sound_not_found", who.lang))
    return web.json_response({"ok": True})


# --- administrators ------------------------------------------------------------------------------


async def admin_balance(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    body = await _json(request)
    target, amount = _int(body.get("memberId")), _int(body.get("amount"))
    action = body.get("action")
    if target is None or amount is None or not 0 <= amount <= MAX_MONEY:
        return fail(400, "bad_request", t("pay_invalid", who.lang))
    if action not in ("give", "take", "set") or (action != "set" and amount == 0):
        return fail(400, "bad_request", t("bad_request", who.lang))
    member = _deps(request).guild.member(target)
    if member is None:
        return fail(404, "not_found", t("member_not_found", who.lang))
    ledger = _deps(request).services.ledger
    await ledger.remember_name(member.id, member.name)
    current = await ledger.balance(member.id)
    wanted = {"give": current + amount, "take": max(0, current - amount), "set": amount}[action]
    await ledger.set_balance(member.id, wanted, admin_id=who.id)
    return web.json_response({"ok": True, "balance": await ledger.balance(member.id)})


async def admin_feature(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    body = await _json(request)
    key, on = body.get("key"), body.get("on")
    if key not in FEATURES or not isinstance(on, bool):
        return fail(400, "bad_request", t("bad_request", who.lang))
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


async def _ai_json(request: web.Request) -> dict[str, Any]:
    deps = _deps(request)
    cfg = deps.services.config
    main, gate = await deps.services.settings.ai_models()
    models = await deps.models().models()
    return {
        "ok": True,
        "aiEnabled": deps.services.llm is not None,
        "model": main or cfg.agent_model,
        "gateModel": gate or cfg.agent_gate_model,
        "defaultModel": cfg.agent_model,
        "defaultGateModel": cfg.agent_gate_model,
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "promptPerMillion": m.prompt_per_million,
                "completionPerMillion": m.completion_per_million,
                "context": m.context,
                "tools": m.tools,
            }
            for m in models
        ],
    }


async def admin_ai(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    if request.method == "POST":
        body = await _json(request)
        settings = _deps(request).services.settings
        catalog = _deps(request).models()
        for field, kind in (("model", "model"), ("gateModel", "gate_model")):
            if field not in body:
                continue
            value = body[field]
            if value is None:
                await settings.set_ai_model(kind, None)
            elif isinstance(value, str) and await catalog.is_known(value.strip()):
                await settings.set_ai_model(kind, value.strip())
            else:
                return fail(400, "bad_request", t("model_invalid", who.lang))
    return web.json_response(await _ai_json(request))


async def admin_prompt(request: web.Request) -> web.Response:
    _, err = await _auth(request, admin=True)
    if err:
        return err
    parts = [
        ("persona", "Persona (economy on)", persona.stable_prefix(economy_on=True)),
        ("persona_off", "Persona (economy off)", persona.stable_prefix(economy_on=False)),
        ("gate", "Router: should Marione answer?", prompts.GATE_SYSTEM),
        ("summary", "Conversation summary", prompts.COMPRESS_SYSTEM),
        ("profiler", "Notes about members", prompts.FACTS_SYSTEM),
    ]
    return web.json_response(
        {"ok": True, "parts": [{"key": k, "title": n, "text": x} for k, n, x in parts]}
    )


async def admin_settings(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    settings = _deps(request).services.settings
    if request.method == "POST":
        code = normalize(str((await _json(request)).get("serverLanguage", "")))
        if code is None:
            return fail(400, "bad_request", t("bad_request", who.lang))
        await settings.set_server_language(code)
    return web.json_response({"ok": True, "serverLanguage": await settings.server_language()})


# --- what Marione remembers (administrators only) ------------------------------------------------


async def memory_members(request: web.Request) -> web.Response:
    _, err = await _auth(request, admin=True)
    if err:
        return err
    offset, limit = _page(request, 20)
    deps = _deps(request)
    total, rows = await deps.services.insight.members(
        request.query.get("q", "")[:60], offset, limit
    )
    items = []
    for r in rows:
        who = deps.guild.member(r.user_id)
        items.append(
            {
                "id": str(r.user_id),
                "name": who.name if who else r.name or str(r.user_id),
                "avatar": who.avatar_url if who else None,
                "facts": r.facts,
                "episodes": r.episodes,
                "messages": r.messages,
            }
        )
    return web.json_response({"ok": True, "total": total, "items": items})


async def memory_member(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    uid = _int(request.query.get("memberId"))
    if uid is None:
        return fail(400, "bad_request", t("member_not_found", who.lang))
    deps = _deps(request)
    insight = deps.services.insight
    offset, limit = _page(request, 20)
    total, lines = await insight.member_lines(uid, offset, limit)
    guild_member = deps.guild.member(uid)
    name = guild_member.name if guild_member else await deps.services.ledger.name_of(uid, str(uid))
    return web.json_response(
        {
            "ok": True,
            "member": {
                "id": str(uid),
                "name": name,
                "avatar": guild_member.avatar_url if guild_member else None,
            },
            "facts": [
                {
                    "id": f.id,
                    "category": f.category,
                    "text": f.text,
                    "confidence": f.confidence,
                    "updatedAt": iso(f.updated_at),
                }
                for f in await insight.facts(uid)
            ],
            "episodes": [
                {"id": e.id, "text": e.text, "at": iso(e.created_at)}
                for e in await insight.episodes(uid)
            ],
            "messages": {
                "total": total,
                "items": [
                    {
                        "channel": deps.guild.channel_name(ln.channel_id) or str(ln.channel_id),
                        "text": ln.content,
                        "at": iso(ln.created_at),
                    }
                    for ln in lines
                ],
            },
        }
    )


async def memory_delete_fact(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    fact_id = _int((await _json(request)).get("id"))
    if fact_id is None or not await _deps(request).services.insight.delete_fact(fact_id):
        return fail(404, "not_found", t("bad_request", who.lang))
    return web.json_response({"ok": True})


async def memory_forget(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    uid = _int((await _json(request)).get("memberId"))
    if uid is None:
        return fail(400, "bad_request", t("member_not_found", who.lang))
    svc = _deps(request).services
    removed = await svc.memory.forget_member(uid) + await svc.chatlog.forget_member(uid)
    return web.json_response({"ok": True, "removed": removed})


async def memory_channels(request: web.Request) -> web.Response:
    _, err = await _auth(request, admin=True)
    if err:
        return err
    deps = _deps(request)
    return web.json_response(
        {
            "ok": True,
            "items": [
                {
                    "id": str(c.channel_id),
                    "name": deps.guild.channel_name(c.channel_id) or str(c.channel_id),
                    "summary": c.summary,
                    "messages": c.messages,
                    "updatedAt": iso(c.updated_at),
                }
                for c in await deps.services.insight.channels()
            ],
        }
    )


async def memory_channel(request: web.Request) -> web.Response:
    who, err = await _auth(request, admin=True)
    if err:
        return err
    channel_id = _int(request.query.get("channelId"))
    if channel_id is None:
        return fail(400, "bad_request", t("bad_request", who.lang))
    offset, limit = _page(request, 30)
    total, lines = await _deps(request).services.insight.channel_lines(channel_id, offset, limit)
    return web.json_response(
        {
            "ok": True,
            "total": total,
            "items": [
                {
                    "author": ln.author_name,
                    "isBot": ln.is_bot,
                    "text": ln.content,
                    "at": iso(ln.created_at),
                }
                for ln in lines
            ],
        }
    )


def add_routes(app: web.Application) -> None:
    r = app.router
    r.add_get("/api/me", me)
    r.add_post("/api/settings/language", set_language)
    r.add_get("/auth/login", auth_login)
    r.add_get("/auth/callback", auth_callback)
    r.add_get("/auth/logout", auth_logout)
    r.add_post("/auth/logout", auth_logout)
    r.add_get("/api/state", state)
    r.add_get("/api/live", live)
    r.add_get("/api/economy/leaderboard", leaderboard_page)
    r.add_get("/api/economy/history", history_page)
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
    r.add_get("/api/entrance/members", entrance_members)
    r.add_get("/api/entrance/list", entrance_list)
    r.add_get("/api/entrance/audio", entrance_audio)
    r.add_post("/api/entrance/add", entrance_add)
    r.add_post("/api/entrance/remove", entrance_remove)
    r.add_post("/api/admin/balance", admin_balance)
    r.add_post("/api/admin/feature", admin_feature)
    r.add_get("/api/admin/usage", admin_usage)
    r.add_get("/api/admin/ai", admin_ai)
    r.add_post("/api/admin/ai", admin_ai)
    r.add_get("/api/admin/ai/prompt", admin_prompt)
    r.add_get("/api/admin/settings", admin_settings)
    r.add_post("/api/admin/settings", admin_settings)
    r.add_get("/api/admin/memory/members", memory_members)
    r.add_get("/api/admin/memory/member", memory_member)
    r.add_post("/api/admin/memory/fact/delete", memory_delete_fact)
    r.add_post("/api/admin/memory/forget", memory_forget)
    r.add_get("/api/admin/memory/channels", memory_channels)
    r.add_get("/api/admin/memory/channel", memory_channel)
