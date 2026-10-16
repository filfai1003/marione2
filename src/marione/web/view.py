"""The JSON the page shows, built from the services (see docs/WEB_API.md)."""

from datetime import UTC, datetime
from typing import Any

from marione.db.sounds import MAX_PER_MEMBER
from marione.domain.roles import TIERS, Tier, next_tier, tier_for
from marione.labels import describe
from marione.ports import GuildMember
from marione.web.deps import WebDeps

LEADERBOARD_SIZE = 50
HISTORY_SIZE = 30


def tier_json(tier: Tier) -> dict[str, Any]:
    return {"key": tier.key, "name": tier.name, "emoji": tier.emoji, "color": tier.hex}


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def member_json(m: GuildMember) -> dict[str, Any]:
    return {"id": str(m.id), "name": m.name, "handle": m.handle, "avatar": m.avatar_url}


async def build_state(deps: WebDeps, me: GuildMember) -> dict[str, Any]:
    svc = deps.services
    ledger = svc.ledger
    balance = await ledger.balance(me.id)
    tier = tier_for(balance)
    upcoming = next_tier(balance)
    rank, count = await ledger.rank_of(me.id)

    top = await ledger.top(LEADERBOARD_SIZE)
    leaderboard = []
    for uid, name, bal in top:
        who = deps.guild.member(uid)
        leaderboard.append(
            {
                "id": str(uid),
                "name": who.name if who else name or str(uid),
                "avatar": who.avatar_url if who else None,
                "bal": bal,
                "tier": tier_json(tier_for(bal)),
                "isMe": uid == me.id,
            }
        )

    members = []
    for uid, _name, bal in await ledger.holders():
        who = deps.guild.member(uid)
        if who is not None and uid != me.id:
            members.append({"id": str(uid), "name": who.name, "avatar": who.avatar_url, "bal": bal})

    history = []
    for entry in await ledger.history(me.id, HISTORY_SIZE):
        other = await ledger.name_of(entry.counterparty, "") if entry.counterparty else None
        history.append(
            {
                "id": entry.id,
                "delta": entry.delta,
                "reason": entry.reason,
                "label": describe(entry.reason, other),
                "with": other or None,
                "at": iso(entry.created_at),
            }
        )

    modules = await svc.settings.flags()
    entrances = await svc.sounds.list(me.id)
    return {
        "ok": True,
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
        "leaderboard": leaderboard,
        "members": members,
        "history": history,
        "sounds": await sounds_json(deps, me.id),
        "soundboardVolume": await svc.settings.soundboard_volume(),
        "entrances": [
            {"name": s.name, "size": s.size, "durationMs": s.duration_ms} for s in entrances
        ],
        "entranceLimit": MAX_PER_MEMBER,
        "modules": modules,
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
