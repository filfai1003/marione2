"""What the model is shown: the persisted window, the quoted message, the server and the money."""

from marione.agent.prompt import ChatContext, render_context
from marione.agent.service import AgentConfig, ChatAgent
from marione.agent.types import ChatMessage, WorldSnapshot
from marione.db.chatlog import ChatLog
from marione.db.ledger import Ledger
from marione.db.memory import MemoryRepo
from marione.db.pool import Pool
from marione.db.settings import SettingsRepo
from tests.agent.test_agent import ANNA, BOT, BRUNO, Clock, Directory, msg
from tests.fakes import ScriptedLLM, reply


class FixedWorld:
    def snapshot(self, channel_id: int) -> WorldSnapshot:
        return WorldSnapshot(
            "venerdì 16 ottobre 2026, 23:11",
            "#general",
            "chiacchiere",
            (("Sala", ("Anna", "Bruno")),),
        )


def make(pool: Pool, llm: ScriptedLLM, clock: Clock, *, world: bool = True) -> ChatAgent:
    return ChatAgent(
        llm=llm,
        ledger=Ledger(pool),
        memory=MemoryRepo(pool),
        settings=SettingsRepo(pool),
        directory=Directory(),
        config=AgentConfig(model="main", gate_model="cheap"),
        bot_id=BOT,
        bot_name=lambda: "Marione",
        clock=clock,
        chatlog=ChatLog(pool),
        world=FixedWorld() if world else None,
    )


def system_text(llm: ScriptedLLM) -> str:
    return "\n".join(m["content"] for m in llm.calls[-1].messages if m["role"] == "system")


class TestRendering:
    def test_world_tiers_and_events_are_rendered(self) -> None:
        ctx = ChatContext(
            balances=[("Anna", 5000)],
            tiers={"Anna": "Sbarca il lunario, #3 of 40"},
            events=["Anna: Mandati a Bruno (-50)"],
            world=FixedWorld().snapshot(1),
        )
        text = render_context(ctx)
        assert "SERVER NOW" in text and "23:11" in text and "#general" in text
        assert "In voice, Sala: Anna, Bruno" in text
        assert "Anna: 5000 Marioncelli (Sbarca il lunario, #3 of 40)" in text
        assert "RECENT MONEY EVENTS" in text and "Mandati a Bruno" in text

    def test_nobody_in_voice(self) -> None:
        assert "Nobody is in a voice channel" in render_context(
            ChatContext(world=WorldSnapshot("oggi", "#x"))
        )


class TestAgentContext:
    async def test_the_model_sees_server_tier_rank_and_money_events(
        self, pool: Pool, clock: Clock
    ) -> None:
        ledger = Ledger(pool)
        await ledger.remember_name(ANNA, "Anna")
        await ledger.remember_name(BRUNO, "Bruno")
        await ledger.credit(ANNA, 5000, "admin_adjust")
        await ledger.pay(ANNA, BRUNO, 50, key="p1")
        llm = ScriptedLLM([reply("ciao")])
        await make(pool, llm, clock).handle(msg("marione ciao", addressed=True))
        text = system_text(llm)
        assert "SERVER NOW" in text and "Sala: Anna, Bruno" in text
        assert "Sbarca il lunario, #1 of 2" in text
        assert "Mandati a Bruno" in text

    async def test_the_quoted_message_is_shown(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([reply("giusto")])
        await make(pool, llm, clock).handle(
            msg(
                "sono d'accordo",
                addressed=True,
                reply_to_id=BRUNO,
                reply_author="Bruno",
                reply_text="la pasta si spezza",
            )
        )
        last = llm.calls[-1].messages[-1]["content"]
        assert 'replying to Bruno: "la pasta si spezza"' in last

    async def test_attachments_are_named_because_the_model_cannot_see_them(
        self, pool: Pool, clock: Clock
    ) -> None:
        llm = ScriptedLLM([reply("bella")])
        await make(pool, llm, clock).handle(
            msg("guarda", addressed=True, attachments=("image: gatto.png",))
        )
        assert "[attached: image: gatto.png]" in llm.calls[-1].messages[-1]["content"]

    async def test_without_a_world_the_prompt_still_works(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([reply("ok")])
        await make(pool, llm, clock, world=False).handle(msg("marione?", addressed=True))
        assert "SERVER NOW" not in system_text(llm)


class TestPersistence:
    async def test_messages_and_replies_are_stored(self, pool: Pool, clock: Clock) -> None:
        llm = ScriptedLLM([reply("eccomi")])
        await make(pool, llm, clock).handle(msg("marione ci sei?", addressed=True, mid=5))
        lines = await ChatLog(pool).recent(10, 10)
        assert [(ln.author_name, ln.content) for ln in lines] == [
            ("Anna", "marione ci sei?"),
            ("Marione", "eccomi"),
        ]
        assert lines[1].is_bot and not lines[0].is_bot

    async def test_a_restart_does_not_lose_the_conversation(self, pool: Pool, clock: Clock) -> None:
        first = ScriptedLLM([reply("uno")])
        await make(pool, first, clock).handle(
            msg("marione parliamo di sugo", addressed=True, mid=1)
        )
        # A brand new agent (the bot restarted) answers the next message.
        second = ScriptedLLM([reply("due")])
        await make(pool, second, clock).handle(
            msg("e del basilico?", addressed=True, mid=2, name="Anna")
        )
        history = [m["content"] for m in second.calls[-1].messages if m["role"] != "system"]
        assert any("parliamo di sugo" in h for h in history)
        assert "uno" in history

    async def test_forgetting_a_member_clears_their_lines_from_the_window(
        self, pool: Pool, clock: Clock
    ) -> None:
        llm = ScriptedLLM([reply("ok")])
        agent = make(pool, llm, clock)
        await agent.handle(msg("marione ciao", addressed=True))
        await agent.forget(ANNA)
        assert all(
            s.window == [] or all(ln.author_id != ANNA for ln in s.window)
            for s in agent._sessions.all()
        )


def test_chat_message_defaults_are_backward_compatible() -> None:
    m = ChatMessage(1, "A", "x", 2, 3)
    assert m.reply_text is None and m.attachments == () and m.channel_name == ""
