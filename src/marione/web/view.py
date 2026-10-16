"""The JSON the page shows, built from the services (see docs/WEB_API.md)."""

from datetime import UTC, datetime
from typing import Any

from marione.domain.roles import TIERS, Tier, next_tier, tier_for
from marione.i18n import LANGS
from marione.labels import describe
from marione.ports import GuildMember
from marione.web.deps import WebDeps

PAGE = 10


def tier_json(tier: Tier) -> dict[str, Any]:
    return {"key": tier.key, "name": tier.name, "emoji": tier.emoji, "color": tier.hex}


def iso(moment: datetime | None) -> str | None:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def member_json(m: GuildMember) -> dict[str, Any]:
    return {"id": str(m.id), "name": m.name, "handle": m.handle, "avatar": m.avatar_url}


async def leaderboard(
    deps: WebDeps, me: int, query: str, offset: int, limit: int
) -> tuple[int, list[dict[str, Any]]]:
    total, rows = await deps.services.ledger.leaderboard_page(query, offset, limit)
    items = []
    for rank, uid, name, bal in rows:
        who = deps.guild.member(uid)
        items.append(
            {
                "rank": rank,
                "id": str(uid),
                "name": who.name if who else name or str(uid),
                "avatar": who.avatar_url if who else None,
                "bal": bal,
                "tier": tier_json(tier_for(bal)),
                "isMe": uid == me,
            }
        )
    return total, items


async def history(
    deps: WebDeps, me: int, lang: str, offset: int, limit: int
) -> tuple[int, list[dict[str, Any]]]:
    ledger = deps.services.ledger
    total, entries = await ledger.history_page(me, offset, limit)
    items = []
    for entry in entries:
        other = await ledger.name_of(entry.counterparty, "") if entry.counterparty else None
        items.append(
            {
                "id": entry.id,
                "delta": entry.delta,
                "reason": entry.reason,
                "label": describe(entry.reason, other, lang),
                "with": other or None,
                "at": iso(entry.created_at),
            }
        )
    return total, items


async def sounds_json(deps: WebDeps, user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "emoji": s.emoji,
            "durationMs": s.duration_ms,
            "fav": s.fav,
            "own": s.creator_id == user_id,
        }
        for s in await deps.services.soundboard.catalog(user_id)
    ]


async def build_state(deps: WebDeps, me: GuildMember, lang: str) -> dict[str, Any]:
    svc = deps.services
    ledger = svc.ledger
    balance = await ledger.balance(me.id)
    tier = tier_for(balance)
    upcoming = next_tier(balance)
    rank, count = await ledger.rank_of(me.id)
    board_total, board = await leaderboard(deps, me.id, "", 0, PAGE)
    history_total, moves = await history(deps, me.id, lang, 0, PAGE)

    members = []
    for uid, _name, bal in await ledger.holders():
        who = deps.guild.member(uid)
        if who is not None and uid != me.id:
            members.append({"id": str(uid), "name": who.name, "avatar": who.avatar_url, "bal": bal})

    return {
        "ok": True,
        "lang": lang,
        "languages": list(LANGS),
        "me": {**member_json(me), "isAdmin": me.is_admin},
        "balance": balance,
        "tier": {
            **tier_json(tier),
            "min": tier.min_balance,
            "next": (
                {
                    "name": upcoming.name,
                    "min": upcoming.min_balance,
                    "missing": upcoming.min_balance - balance,
                }
                if upcoming
                else None
            ),
        },
        "rank": rank,
        "memberCount": count,
        "leaderboard": board,
        "leaderboardTotal": board_total,
        "members": members,
        "history": moves,
        "historyTotal": history_total,
        "sounds": await sounds_json(deps, me.id),
        "soundboardVolume": await svc.settings.soundboard_volume(),
        "modules": await svc.settings.flags(),
        "roles": [
            {"name": t.name, "min": t.min_balance, "color": t.hex, "emoji": t.emoji} for t in TIERS
        ],
        "rob": {
            "cooldownSeconds": await svc.economy.rob_cooldown(me.id),
            "minAmount": svc.economy_rules.robbery.min_amount,
        },
        "inVoice": me.voice_channel is not None,
        "voiceChannel": me.voice_channel,
    }
