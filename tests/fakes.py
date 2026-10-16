"""Test doubles shared by the test files."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from marione.llm.types import LLMResponse, Message, ToolCall, ToolSpec, Usage


def reply(
    text: str | None = None,
    *,
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    cost: str = "0.001",
    model: str = "fake/model",
) -> LLMResponse:
    return LLMResponse(
        text=text,
        model=model,
        usage=Usage(10, 5, Decimal(cost)),
        tool_calls=[
            ToolCall(f"call_{i}", name, args) for i, (name, args) in enumerate(calls or [])
        ],
    )


@dataclass
class Call:
    role: str
    model: str
    messages: list[Message]
    tools: list[ToolSpec] | None
    json_mode: bool


@dataclass
class ScriptedLLM:
    """Answers with the given responses, in order; an Exception in the list is raised."""

    script: list[LLMResponse | Exception]
    calls: list[Call] = field(default_factory=list)

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
    ) -> LLMResponse:
        self.calls.append(Call(role, model, [dict(m) for m in messages], tools, json_mode))
        if not self.script:
            raise AssertionError("the model was called more times than the test expected")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
