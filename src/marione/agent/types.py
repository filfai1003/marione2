from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ChatMessage:
    """One chat message, already stripped of everything Discord-specific."""

    author_id: int
    author_name: str
    content: str
    channel_id: int
    message_id: int
    is_bot: bool = False
    addressed: bool = False  # mentions the bot, replies to it, or names it
    reply_to_id: int | None = None  # author of the message this one answers
    mentioned_ids: tuple[int, ...] = ()
    reply_to_message_id: int | None = None
    reply_text: str | None = None  # what that message said (the model must see what is answered)
    reply_author: str | None = None
    attachments: tuple[str, ...] = ()  # e.g. "image: foto.png": the model cannot see them
    channel_name: str = ""


@dataclass(frozen=True)
class MemberRef:
    id: int
    name: str


@dataclass(frozen=True)
class WorldSnapshot:
    """What is going on in the server right now, as plain text the prompt can show."""

    local_time: str  # "venerdì 16 ottobre 2026, 23:11"
    channel: str  # "#general"
    topic: str | None = None
    voice: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (voice channel, member names)


class WorldView(Protocol):
    def snapshot(self, channel_id: int) -> WorldSnapshot: ...


class MemberDirectory(Protocol):
    """How the agent finds a server member by the name the model wrote."""

    def resolve(self, name: str) -> MemberRef | None: ...


@dataclass(frozen=True)
class ActionRecord:
    """An economic action the agent really performed (what the cog announces)."""

    kind: str  # "gift" | "fine"
    target: MemberRef
    amount: int
    group_id: UUID
    comment: str


@dataclass
class Reply:
    text: str | None
    actions: list[ActionRecord] = field(default_factory=list)
