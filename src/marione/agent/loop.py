"""The agent loop: ask the model, run the tools it asks for, give it the results, repeat.

It stops when the model answers with plain text, calls `stay_silent`, or after a fixed number of
steps (a runaway loop costs money). Results fed back to the model are cut to a safe length.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from marione.agent.tools import STAY_SILENT, ToolContext, ToolRegistry
from marione.agent.types import ActionRecord
from marione.llm.types import LLMClient, Message


@dataclass
class AgentResult:
    text: str | None
    silent: bool = False
    steps: int = 0
    actions: list[ActionRecord] = field(default_factory=list)


def _truncate(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    return content[:limit] + "… [cut]"


async def run_agent(
    *,
    llm: LLMClient,
    role: str,
    model: str,
    fallbacks: list[str],
    messages: list[Message],
    registry: ToolRegistry,
    ctx: ToolContext,
    max_tokens: int,
    temperature: float,
) -> AgentResult:
    history = list(messages)
    pending_text: str | None = None
    steps = 0
    for _ in range(ctx.rules.max_tool_steps):
        steps += 1
        response = await llm.complete(
            role=role,
            model=model,
            messages=history,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=registry.specs(),
            fallbacks=fallbacks,
        )
        if response.text and response.text.strip():
            pending_text = response.text.strip()

        if any(c.name == STAY_SILENT for c in response.tool_calls):
            return AgentResult(None, silent=True, steps=steps, actions=ctx.actions)
        if not response.tool_calls:
            return AgentResult(pending_text, steps=steps, actions=ctx.actions)

        history.append(
            {
                "role": "assistant",
                "content": response.text,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in response.tool_calls
                ],
            }
        )
        for call in response.tool_calls:
            result, _ok = await registry.execute(call, ctx)
            content: Any = _truncate(
                json.dumps(result, ensure_ascii=False), ctx.rules.max_tool_result_chars
            )
            history.append({"role": "tool", "tool_call_id": call.id, "content": content})

    # Out of steps: say what the model already wanted to say, if anything.
    return AgentResult(pending_text, steps=steps, actions=ctx.actions)
