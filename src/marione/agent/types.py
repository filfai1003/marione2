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
    reply_to_id: int | None = None
    mentioned_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class MemberRef:
    id: int
    name: str


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
