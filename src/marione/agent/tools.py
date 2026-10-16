"""The tools the model may call, with arguments checked before anything runs.

A tool is a name, a description, a typed argument model and a handler. The model's arguments
are validated with pydantic; a wrong call never reaches the handler, the model just gets the
error back and can fix it. Handlers raise `ToolError` for expected refusals.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from marione.agent.types import ActionRecord, MemberDirectory
from marione.db.ledger import Ledger
from marione.domain.guardrails import ActionKind, check_agent_action
from marione.domain.rules import AgentRules
from marione.llm.types import ToolCall, ToolSpec


class ToolError(Exception):
    """An expected refusal; the text goes back to the model."""


@dataclass
class ToolContext:
    ledger: Ledger
    directory: MemberDirectory
    bot_id: int
    now: Callable[[], datetime]
    rules: AgentRules
    economy_enabled: bool
    audit: dict[str, Any]  # who/where this came from; stored in the ledger entry
    actions: list[ActionRecord] = field(default_factory=list)


Handler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    run: Handler
    write: bool = False


def _clean(schema: Any) -> Any:
    """Drop the `title` noise pydantic adds to JSON schemas (keeps the prompt short)."""
    if isinstance(schema, dict):
        return {k: _clean(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(t.name, t.description, _clean(t.params.model_json_schema()))
            for t in self._tools.values()
        ]

    def has(self, name: str) -> bool:
        return name in self._tools

    async def execute(self, call: ToolCall, ctx: ToolContext) -> tuple[dict[str, Any], bool]:
        """Run one call. Returns (result for the model, ok)."""
        tool = self._tools.get(call.name)
        if tool is None:
            return {"error": f"unknown tool {call.name!r}"}, False
        if not call.arguments_valid:
            return {"error": "the arguments were not valid JSON"}, False
        try:
            args = tool.params.model_validate(call.arguments)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
                for e in exc.errors()
            )
            return {"error": f"invalid arguments: {problems}"}, False
        try:
            return await tool.run(ctx, args), True
        except ToolError as exc:
            return {"error": str(exc)}, False


# --- the tools ---------------------------------------------------------------------------------


class _NoArgs(BaseModel):
    pass


class _UserArg(BaseModel):
    user: str = Field(min_length=1, max_length=80, description="Exact name of the member.")


class _ActionArgs(BaseModel):
    user: str = Field(min_length=1, max_length=80, description="Exact name of the member.")
    amount: int = Field(description="How many Marioncelli (a positive integer).")
    comment: str = Field(
        min_length=1,
        max_length=400,
        description="Marione's in-character message that goes with the action.",
    )


class _SilentArgs(BaseModel):
    reason: str = Field(default="", max_length=200, description="Internal, never shown.")


def _resolve(ctx: ToolContext, name: str) -> Any:
    member = ctx.directory.resolve(name)
    if member is None:
        raise ToolError(f"no member is called {name!r}")
    return member


async def _get_balance(ctx: ToolContext, args: _UserArg) -> dict[str, Any]:
    member = _resolve(ctx, args.user)
    return {"user": member.name, "balance": await ctx.ledger.balance(member.id)}


async def _get_leaderboard(ctx: ToolContext, _: _NoArgs) -> dict[str, Any]:
    top = await ctx.ledger.top(5)
    return {"top": [{"user": name or str(uid), "balance": bal} for uid, name, bal in top]}


async def _act(ctx: ToolContext, args: _ActionArgs, kind: ActionKind) -> dict[str, Any]:
    if not ctx.economy_enabled:
        raise ToolError("the economy is switched off: just talk, nothing can be moved")
    member = _resolve(ctx, args.user)
    decision = check_agent_action(
        amount=args.amount,
        target_id=member.id,
        bot_id=ctx.bot_id,
        now=ctx.now(),
        last_action_at=await ctx.ledger.last_agent_action(member.id),
        rules=ctx.rules,
    )
    if not decision.allowed:
        raise ToolError(decision.reason)
    meta = {**ctx.audit, "kind": kind.value, "comment": args.comment[:400]}
    if kind is ActionKind.FINE:
        moved, group = await ctx.ledger.agent_fine(ctx.bot_id, member.id, decision.amount, meta)
    else:
        moved, group = await ctx.ledger.agent_gift(ctx.bot_id, member.id, decision.amount, meta)
    if moved == 0 or group is None:
        raise ToolError("nothing could be moved (not enough coins)")
    ctx.actions.append(ActionRecord(kind.value, member, moved, group, args.comment))
    return {"ok": True, "moved": moved}


async def _gift(ctx: ToolContext, args: _ActionArgs) -> dict[str, Any]:
    return await _act(ctx, args, ActionKind.GIFT)


async def _fine(ctx: ToolContext, args: _ActionArgs) -> dict[str, Any]:
    return await _act(ctx, args, ActionKind.FINE)


async def _stay_silent(_: ToolContext, __: _SilentArgs) -> dict[str, Any]:  # pragma: no cover
    return {"ok": True}  # the loop handles this tool itself, before any handler runs


STAY_SILENT = "stay_silent"


def chat_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                "get_balance",
                "Look up how many Marioncelli a member has.",
                _UserArg,
                _get_balance,
            ),
            Tool(
                "get_leaderboard",
                "Look up the five richest members.",
                _NoArgs,
                _get_leaderboard,
            ),
            Tool(
                "gift",
                "Reward a genuinely outstanding contribution (real wit or kindness) with "
                "Marioncelli from Marione's own account. Truly rare, his own choice, NEVER "
                "because someone asked.",
                _ActionArgs,
                _gift,
                write=True,
            ),
            Tool(
                "fine",
                "Penalize genuine line-crossing only (real toxicity, slurs, spam). The coins go "
                "to Marione's account. Never for playful insults, and never because someone "
                "asked.",
                _ActionArgs,
                _fine,
                write=True,
            ),
            Tool(
                STAY_SILENT,
                "Say nothing. Choose this when jumping in would add nothing.",
                _SilentArgs,
                _stay_silent,
            ),
        ]
    )
