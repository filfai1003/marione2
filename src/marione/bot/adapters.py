"""Translation between Discord objects and the plain types the agent understands."""

import re
from collections.abc import Callable, Iterable
from typing import Any

from marione.agent.types import ActionRecord, ChatMessage, MemberRef, Reply
from marione.domain.triggers import is_called


def unit(n: int) -> str:
    return "Marioncello" if n == 1 else "Marioncelli"


def to_chat_message(message: Any, bot_id: int, triggers: Iterable[re.Pattern[str]]) -> ChatMessage:
    """A discord.Message as a ChatMessage. Addressed = mention, reply to the bot, or its name."""
    content = message.clean_content or message.content or ""
    addressed = any(u.id == bot_id for u in message.mentions)
    reply_to: int | None = None
    ref = message.reference
    resolved = getattr(ref, "resolved", None)
    if resolved is not None and hasattr(resolved, "author"):
        reply_to = resolved.author.id
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
    )


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
