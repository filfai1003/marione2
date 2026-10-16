import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from marione.agent.loop import run_agent
from marione.agent.prefilter import Level0, classify
from marione.agent.profiler import parse_facts
from marione.agent.prompt import ChatContext, Line, build_messages, parse_gate
from marione.agent.service import EXHAUSTED_REPLY, AgentConfig, ChatAgent
from marione.agent.tools import ToolContext, chat_registry
from marione.agent.types import ChatMessage, MemberRef
from marione.db.ledger import Ledger
from marione.db.memory import Fact, MemoryRepo
from marione.db.pool import Pool
from marione.db.settings import SettingsRepo
from marione.domain.rules import AgentRules
from marione.llm.types import BudgetExceeded, ProviderError
from tests.fakes import ScriptedLLM, reply

BOT = 999
ANNA, BRUNO = 1, 2


class Directory:
    def __init__(self) -> None:
        self.members = {"anna": MemberRef(ANNA, "Anna"), "bruno": MemberRef(BRUNO, "Bruno")}

    def resolve(self, name: str) -> MemberRef | None:
        return self.members.get(name.strip().lower())


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.dt = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def mono(self) -> float:
        return self.t

    def now(self) -> datetime:
        return self.dt

    def advance(self, seconds: float) -> None:
        self.t += seconds
        self.dt += timedelta(seconds=seconds)


def msg(
    text: str,
    *,
    author: int = ANNA,
    name: str = "Anna",
    addressed: bool = False,
    mid: int = 1,
    **kw: Any,
) -> ChatMessage:
    return ChatMessage(author, name, text, channel_id=10, message_id=mid, addressed=addressed, **kw)


def make_agent(pool: Pool, llm: ScriptedLLM, clock: Clock, **cfg: Any) -> ChatAgent:
    return ChatAgent(
        llm=llm,
        ledger=Ledger(pool),
        memory=MemoryRepo(pool),
        settings=SettingsRepo(pool),
        directory=Directory(),
        config=AgentConfig(model="main", gate_model="cheap", **cfg),
        bot_id=BOT,
        bot_name=lambda: "Marione",
        clock=clock,
    )


def tool_ctx(pool: Pool, clock: Clock, economy: bool = True) -> ToolContext:
    return ToolContext(
        ledger=Ledger(pool),
        directory=Directory(),
        bot_id=BOT,
        now=clock.now,
        rules=AgentRules(),
        economy_enabled=economy,
        audit={"source": "test"},
    )


# --- pure pieces -------------------------------------------------------------------------------


class TestPrefilter:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("ciao a tutti", Level0.GATE),
            ("ok", Level0.DISCARD),
            ("!help", Level0.DISCARD),
            ("/marione", Level0.DISCARD),
            ("https://example.com/x", Level0.DISCARD),
            ("guarda https://example.com/x", Level0.GATE),
            ("😂😂😂", Level0.DISCARD),
        ],
    )
    def test_classify(self, text: str, expected: Level0) -> None:
        assert classify(msg(text)) == expected

    def test_addressed_always_goes_through_and_bots_never(self) -> None:
        assert classify(msg("ok", addressed=True)) == Level0.ADDRESSED
        assert classify(msg("ciao a tutti", **{})) == Level0.GATE
        bot = ChatMessage(BOT, "Marione", "ciao", 10, 1, is_bot=True, addressed=True)
        assert classify(bot) == Level0.DISCARD


def test_parse_gate() -> None:
    assert parse_gate('{"reply": true}') is True
    assert parse_gate('{"reply": false}') is False
    assert parse_gate("sure!") is None
    assert parse_gate('{"reply": "yes"}') is None
    assert parse_gate(None) is None


def test_parse_facts_keeps_good_items_and_drops_bad_ones() -> None:
    raw = json.dumps(
        {
            "facts": [
                {"category": "likes", "text": " pasta ", "confidence": 4},
                {"category": "secrets", "text": "x", "confidence": 3},
                {"category": "notes", "text": "", "confidence": 3},
                {"category": "notes", "text": "ok", "confidence": 99},
                "garbage",
            ]
        }
    )
    assert parse_facts(raw) == [Fact("likes", "pasta", 4), Fact("notes", "ok", 5)]
    assert parse_facts("not json") == []
    assert parse_facts('{"facts": "no"}') == []
    assert parse_facts(None) == []


def test_build_messages_orders_prefix_context_history_current() -> None:
    history = [Line(ANNA, "Anna", "ciao"), Line(BOT, "Marione", "eh")]
    msgs = build_messages(
        economy_on=True,
        context=ChatContext(balances=[("Anna", 5)]),
        history=history,
        bot_id=BOT,
        current="Anna: e quindi?",
        expect_reply=True,
    )
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "system", "user", "assistant", "system", "user"]
    assert msgs[3]["content"] == "eh"  # the bot's own line carries no name prefix
    assert "Anna: 5 Marioncelli" in msgs[1]["content"]
    assert msgs[-1]["content"] == "Anna: e quindi?"


# --- tools and loop ----------------------------------------------------------------------------


class TestTools:
    async def test_unknown_tool_and_bad_arguments_go_back_to_the_model(
        self, pool: Pool, clock: Clock
    ) -> None:
        reg, ctx = chat_registry(), tool_ctx(pool, clock)
        from marione.llm.types import ToolCall

        r, ok = await reg.execute(ToolCall("1", "nope", {}), ctx)
        assert not ok and "unknown" in r["error"]
        r, ok = await reg.execute(ToolCall("2", "gift", {"user": "anna"}), ctx)
        assert not ok and "invalid arguments" in r["error"]
        r, ok = await reg.execute(ToolCall("3", "gift", {}, arguments_valid=False), ctx)
        assert not ok and "JSON" in r["error"]

    async def test_specs_have_names_and_schemas_without_titles(self) -> None:
        specs = {s.name: s for s in chat_registry().specs()}
        assert set(specs) == {"get_balance", "get_leaderboard", "gift", "fine", "stay_silent"}
        assert "title" not in json.dumps(specs["gift"].parameters)
        assert set(specs["gift"].parameters["required"]) == {"user", "amount", "comment"}


class TestLoop:
    async def run(self, pool: Pool, clock: Clock, script: list[Any], economy: bool = True) -> Any:
        ctx = tool_ctx(pool, clock, economy)
        llm = ScriptedLLM(script)
        result = await run_agent(
            llm=llm,
            role="responder",
            model="m",
            fallbacks=[],
            messages=[{"role": "user", "content": "x"}],
            registry=chat_registry(),
            ctx=ctx,
            max_tokens=50,
            temperature=0.5,
        )
        return result, llm

    async def test_plain_text_answer(self, pool: Pool, clock: Clock) -> None:
        result, llm = await self.run(pool, clock, [reply("vabbè")])
        assert (result.text, result.silent, result.steps) == ("vabbè", False, 1)
        assert len(llm.calls) == 1

    async def test_stay_silent_stops_at_once(self, pool: Pool, clock: Clock) -> None:
        result, llm = await self.run(pool, clock, [reply(calls=[("stay_silent", {})])])
        assert result.silent and result.text is None and len(llm.calls) == 1

    async def test_read_tool_result_is_given_back_to_the_model(
        self, pool: Pool, clock: Clock
    ) -> None:
        await Ledger(pool).credit(ANNA, 42, "chat_reward")
        result, llm = await self.run(
            pool,
            clock,
            [reply(calls=[("get_balance", {"user": "Anna"})]), reply("ha 42 sold1")],
        )
        assert result.text == "ha 42 sold1" and result.steps == 2
        tool_message = llm.calls[1].messages[-1]
        assert (
            tool_message["role"] == "tool" and json.loads(tool_message["content"])["balance"] == 42
        )

    async def test_fine_moves_money_records_audit_and_keeps_the_comment(
        self, pool: Pool, clock: Clock
    ) -> None:
        ledger = Ledger(pool)
        await ledger.credit(BRUNO, 100, "chat_reward")
        call = ("fine", {"user": "Bruno", "amount": 30, "comment": "ti sta bene"})
        result, _ = await self.run(pool, clock, [reply(calls=[call]), reply("ti sta bene")])
        assert result.text == "ti sta bene"
        assert [(a.kind, a.target.id, a.amount) for a in result.actions] == [("fine", BRUNO, 30)]
        assert (await ledger.balance(BRUNO), await ledger.balance(BOT)) == (70, 30)
        entry = (await ledger.history(BRUNO))[0]
        assert entry.meta["source"] == "test" and entry.meta["comment"] == "ti sta bene"
        assert await ledger.audit() == []

    async def test_amount_is_capped_by_the_hard_rule(self, pool: Pool, clock: Clock) -> None:
        ledger = Ledger(pool)
        await ledger.credit(BRUNO, 1000, "chat_reward")
        call = ("fine", {"user": "Bruno", "amount": 900, "comment": "x"})
        result, _ = await self.run(pool, clock, [reply(calls=[call]), reply("ok")])
        assert result.actions[0].amount == 200

    async def test_second_action_on_the_same_member_is_refused_by_the_cooldown(
        self, pool: Pool, clock: Clock
    ) -> None:
        ledger = Ledger(pool)
        await ledger.credit(BRUNO, 1000, "chat_reward")
        call = ("fine", {"user": "Bruno", "amount": 10, "comment": "x"})
        script = [reply(calls=[call]), reply(calls=[call]), reply("ok")]
        result, llm = await self.run(pool, clock, script)
        assert len(result.actions) == 1
        refusal = json.loads(llm.calls[2].messages[-1]["content"])
        assert "a moment ago" in refusal["error"]

    async def test_cannot_act_on_itself_or_with_economy_off(self, pool: Pool, clock: Clock) -> None:
        ledger = Ledger(pool)
        await ledger.credit(BRUNO, 100, "chat_reward")
        call = ("fine", {"user": "Bruno", "amount": 10, "comment": "x"})
        result, llm = await self.run(pool, clock, [reply(calls=[call]), reply("ok")], economy=False)
        assert result.actions == [] and await ledger.balance(BRUNO) == 100
        assert "switched off" in json.loads(llm.calls[1].messages[-1]["content"])["error"]

    async def test_unknown_member_is_an_error_not_a_crash(self, pool: Pool, clock: Clock) -> None:
        call = ("gift", {"user": "Nessuno", "amount": 5, "comment": "x"})
        result, llm = await self.run(pool, clock, [reply(calls=[call]), reply("boh")])
        assert result.text == "boh" and result.actions == []
        assert "no member" in json.loads(llm.calls[1].messages[-1]["content"])["error"]

    async def test_a_runaway_model_is_stopped_after_the_step_limit(
        self, pool: Pool, clock: Clock
    ) -> None:
        loop_call = reply("ancora", calls=[("get_leaderboard", {})])
        result, llm = await self.run(pool, clock, [loop_call] * AgentRules().max_tool_steps)
        assert len(llm.calls) == AgentRules().max_tool_steps
        assert result.text == "ancora"  # keeps what it wanted to say


# --- the whole service -------------------------------------------------------------------------


class TestService:
    async def test_discarded_noise_never_reaches_the_model(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([])
        agent = make_agent(pool, llm, clock)
        assert await agent.handle(msg("ok")) is None
        assert llm.calls == []

    async def test_addressed_message_skips_the_gate_and_gets_a_reply(
        self, pool: Pool, clock: Clock
    ) -> None:
        llm = ScriptedLLM([reply("marione: che vuoi")])
        agent = make_agent(pool, llm, clock)
        out = await agent.handle(msg("marione ci sei?", addressed=True))
        assert out is not None and out.text == "che vuoi"  # speaker label stripped
        assert [c.role for c in llm.calls] == ["responder"]
        assert llm.calls[0].model == "main"

    async def test_gate_no_means_silence_and_costs_one_cheap_call(
        self, pool: Pool, clock: Clock
    ) -> None:
        llm = ScriptedLLM([reply('{"reply": false}')])
        agent = make_agent(pool, llm, clock)
        assert await agent.handle(msg("anna hai visto bruno oggi")) is None
        assert [(c.role, c.model, c.json_mode) for c in llm.calls] == [("gate", "cheap", True)]

    async def test_gate_yes_runs_the_responder(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([reply('{"reply": true}'), reply("lol")])
        agent = make_agent(pool, llm, clock)
        out = await agent.handle(msg("che noia questa giornata"))
        assert out is not None and out.text == "lol"
        assert [c.role for c in llm.calls] == ["gate", "responder"]

    async def test_gate_failure_or_garbage_stays_quiet(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([ProviderError("down"), reply("maybe?")])
        agent = make_agent(pool, llm, clock)
        assert await agent.handle(msg("che noia questa giornata")) is None
        assert await agent.handle(msg("che noia questa giornata due", mid=2)) is None
        assert [c.role for c in llm.calls] == ["gate", "gate"]

    async def test_model_choosing_silence_sends_nothing(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([reply(calls=[("stay_silent", {})])])
        agent = make_agent(pool, llm, clock)
        assert await agent.handle(msg("marione?", addressed=True)) is None

    async def test_followup_after_the_bot_spoke_skips_the_gate(
        self, pool: Pool, clock: Clock
    ) -> None:
        llm = ScriptedLLM([reply("ciao"), reply("dimmi")])
        agent = make_agent(pool, llm, clock)
        await agent.handle(msg("marione!", addressed=True))
        clock.advance(10)
        out = await agent.handle(msg("allora?", mid=2))  # not addressed, but a live exchange
        assert out is not None and out.text == "dimmi"
        assert [c.role for c in llm.calls] == ["responder", "responder"]

    async def test_followup_expires(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([reply("ciao"), reply('{"reply": false}')])
        agent = make_agent(pool, llm, clock)
        await agent.handle(msg("marione!", addressed=True))
        clock.advance(500)
        assert await agent.handle(msg("allora com'è andata", mid=2)) is None
        assert llm.calls[1].role == "gate"

    @pytest.mark.parametrize("error", [BudgetExceeded("limit"), ProviderError("down")])
    async def test_when_spoken_to_and_the_model_is_unavailable_it_says_so(
        self, pool: Pool, clock: Clock, error: Exception
    ) -> None:
        agent = make_agent(pool, ScriptedLLM([error]), clock)
        out = await agent.handle(msg("marione ci sei?", addressed=True))
        assert out is not None and out.text == EXHAUSTED_REPLY

    async def test_chime_in_with_unavailable_model_is_silent(
        self, pool: Pool, clock: Clock
    ) -> None:
        agent = make_agent(
            pool, ScriptedLLM([reply('{"reply": true}'), BudgetExceeded("x")]), clock
        )
        assert await agent.handle(msg("che noia questa giornata")) is None

    async def test_feature_switch_turns_the_agent_off(self, pool: Pool, clock: Clock) -> None:
        await SettingsRepo(pool).set_enabled("agent", False)
        llm = ScriptedLLM([])
        agent = make_agent(pool, llm, clock)
        assert await agent.handle(msg("marione!", addressed=True)) is None
        assert llm.calls == []

    async def test_context_contains_only_involved_members(self, pool: Pool, clock: Clock) -> None:
        ledger, memory = Ledger(pool), MemoryRepo(pool)
        await ledger.remember_name(BRUNO, "Bruno")
        await ledger.credit(ANNA, 7, "chat_reward")
        await ledger.credit(BRUNO, 8, "chat_reward")
        await ledger.credit(3, 9, "chat_reward")  # a third member who is NOT involved
        await memory.add_fact(ANNA, Fact("likes", "le polpette", 4))
        await memory.add_fact(3, Fact("likes", "segreto altrui", 4))
        llm = ScriptedLLM([reply("ok")])
        agent = make_agent(pool, llm, clock)
        await agent.handle(msg("marione guarda", addressed=True, mentioned_ids=(BRUNO,)))
        context = llm.calls[0].messages[1]["content"]
        assert "Anna: 7" in context and "Bruno: 8" in context
        assert "le polpette" in context
        assert "segreto altrui" not in context and ": 9 Marioncelli" not in context

    async def test_maintenance_summarises_then_closes_idle_conversations(
        self, pool: Pool, clock: Clock
    ) -> None:
        memory = MemoryRepo(pool)
        llm = ScriptedLLM(
            [reply("Anna e Bruno parlano di polpette e di quanto sia lunga la giornata.")]
        )
        agent = make_agent(pool, llm, clock, compact_at=4, compact_keep=2, idle_seconds=100)
        # going through handle() would cost model calls for each message: add them directly
        session = agent._sessions.get(10, clock.mono())
        for i in range(6):
            session.add(Line(ANNA, "Anna", f"messaggio {i}"), clock.mono())
        await agent.maintenance()
        assert llm.calls[0].role == "compressor"
        assert len(session.window) == 2  # only the newest are kept raw
        assert "polpette" in await memory.summary(10)
        clock.advance(500)
        await agent.maintenance()
        assert agent._sessions.find(10) is None
        assert await memory.summary(10) == ""
        assert [e.text for e in await memory.episodes_for([ANNA])] != []

    async def test_maintenance_turns_messages_into_facts_and_forget_erases_them(
        self, pool: Pool, clock: Clock
    ) -> None:
        memory = MemoryRepo(pool)
        facts = json.dumps({"facts": [{"category": "likes", "text": "il calcio", "confidence": 4}]})
        llm = ScriptedLLM([ProviderError("down"), reply(facts)])
        agent = make_agent(pool, llm, clock, profile_msg_threshold=3)
        for i in range(3):
            await agent._note_member(msg(f"parlo di calcio {i}"))
        clock.advance(2000)
        await agent.maintenance()  # model down: nothing lost, nothing learned
        assert await memory.facts_for([ANNA]) == {}
        await agent.maintenance()  # retried
        assert (await memory.facts_for([ANNA]))[ANNA] == [Fact("likes", "il calcio", 4)]
        assert await agent.forget(ANNA) == 1
        assert await memory.facts_for([ANNA]) == {}
