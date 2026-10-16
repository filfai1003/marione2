"""Translation between Discord objects and the plain types the agent understands."""

import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import discord

from marione.agent.types import ActionRecord, ChatMessage, MemberRef, Reply, WorldSnapshot
from marione.domain.triggers import is_called


def unit(n: int) -> str:
    return "Marioncello" if n == 1 else "Marioncelli"


def to_chat_message(message: Any, bot_id: int, triggers: Iterable[re.Pattern[str]]) -> ChatMessage:
    """A discord.Message as a ChatMessage. Addressed = mention, reply to the bot, or its name."""
    content = message.clean_content or message.content or ""
    addressed = any(u.id == bot_id for u in message.mentions)
    reply_to: int | None = None
    reply_message_id: int | None = None
    reply_text: str | None = None
    reply_author: str | None = None
    ref = message.reference
    resolved = getattr(ref, "resolved", None)
    if resolved is not None and hasattr(resolved, "author"):
        reply_to = resolved.author.id
        reply_message_id = getattr(resolved, "id", None)
        reply_text = (getattr(resolved, "clean_content", None) or "").strip() or None
        reply_author = resolved.author.display_name
        if reply_to == bot_id:
            addressed = True
    if not addressed and is_called(content, triggers):
        addressed = True
    return ChatMessage(
        author_id=message.author.id,
        author_name=message.author.display_name,
        content=content,
        channel_id=message.channel.id,
        message_id=message.id,
        is_bot=bool(message.author.bot),
        addressed=addressed,
        reply_to_id=reply_to,
        mentioned_ids=tuple(u.id for u in message.mentions if u.id != bot_id),
        reply_to_message_id=reply_message_id,
        reply_text=reply_text,
        reply_author=reply_author,
        attachments=tuple(_describe_attachment(x) for x in message.attachments),
        channel_name=getattr(message.channel, "name", "") or "",
    )


def _describe_attachment(attachment: Any) -> str:
    kind = (attachment.content_type or "file").split("/")[0]
    return f"{kind}: {attachment.filename}"


def action_headline(action: ActionRecord, bot_name: str) -> str:
    n = f"**{action.amount} {unit(action.amount)}**"
    if action.kind == "fine":
        return f"⚖️ **{bot_name}** multa **{action.target.name}** di {n}"
    return f"🎁 **{bot_name}** regala {n} a **{action.target.name}**"


def format_reply(reply: Reply, bot_name: str) -> str:
    """One public message: what Marione did (if anything), then his in-character line."""
    heads = [action_headline(a, bot_name) for a in reply.actions]
    line = reply.text or (reply.actions[-1].comment if reply.actions else "")
    if len(heads) == 1 and line:
        return f"{heads[0]} — {line}"
    return "\n".join([*heads, line] if line else heads)


class GuildDirectory:
    """Finds a server member from the name the model wrote. Ambiguous names resolve to nobody:
    a wrong guess here would fine the wrong person."""

    def __init__(self, guild_getter: Callable[[], Any]) -> None:
        self._guild = guild_getter

    def resolve(self, name: str) -> MemberRef | None:
        guild = self._guild()
        wanted = name.strip().lower()
        if guild is None or not wanted:
            return None
        humans = [m for m in guild.members if not m.bot]
        exact = [m for m in humans if wanted in (m.display_name.lower(), m.name.lower())]
        matches = exact or [m for m in humans if wanted in m.display_name.lower()]
        if len(matches) != 1:
            return None
        return MemberRef(matches[0].id, matches[0].display_name)


_WEEKDAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MONTHS = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)


def italian_time(moment: datetime) -> str:
    return (
        f"{_WEEKDAYS[moment.weekday()]} {moment.day} {_MONTHS[moment.month - 1]} "
        f"{moment.year}, {moment.hour:02d}:{moment.minute:02d}"
    )


class DiscordWorld:
    """What is happening in the server right now: time, the channel, who is in voice."""

    def __init__(
        self, guild_getter: Callable[[], Any], tz: ZoneInfo, now: Callable[[], datetime]
    ) -> None:
        self._guild = guild_getter
        self._tz = tz
        self._now = now

    def snapshot(self, channel_id: int) -> WorldSnapshot:
        guild = self._guild()
        channel = guild.get_channel(channel_id) if guild is not None else None
        voice: list[tuple[str, tuple[str, ...]]] = []
        if guild is not None:
            for vc in guild.voice_channels:
                names = tuple(m.display_name for m in vc.members if not m.bot)
                if names:
                    voice.append((vc.name, names))
        online: list[str] = []
        if guild is not None:
            for m in guild.members:
                if m.bot or str(getattr(m, "status", "offline")) in ("offline", "invisible"):
                    continue
                games = [
                    a.name
                    for a in getattr(m, "activities", ())
                    if isinstance(a, discord.Game | discord.Streaming) and a.name
                ]
                online.append(f"{m.display_name} (playing {games[0]})" if games else m.display_name)
        return WorldSnapshot(
            local_time=italian_time(self._now().astimezone(self._tz)),
            online=tuple(online[:25]),
            channel=f"#{channel.name}" if channel is not None else "(unknown)",
            topic=(getattr(channel, "topic", None) or None),
            voice=tuple(voice),
        )
