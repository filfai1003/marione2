"""What the rest of the bot knows about a model call. No provider details leak past here."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

Message = dict[str, Any]  # OpenAI chat format: {"role": ..., "content": ...}


class LLMError(Exception):
    """Base of every failure of a model call."""


class RateLimited(LLMError):
    """The provider asked us to slow down (HTTP 429)."""


class OutOfCredits(LLMError):
    """The OpenRouter account has no credit left (HTTP 402)."""


class ProviderError(LLMError):
    """Any other provider failure: a server error, a timeout, an unreadable answer."""


class BudgetExceeded(LLMError):
    """Our own daily or monthly spending limit is reached; no call was made."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    arguments_valid: bool = True  # False when the model sent arguments that are not JSON


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Decimal = Decimal(0)  # the real cost, as the provider reports it


@dataclass(frozen=True)
class LLMResponse:
    text: str | None
    model: str
    usage: Usage
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_mode: bool = False,
        fallbacks: list[str] | None = None,
    ) -> LLMResponse: ...
