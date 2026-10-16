"""The chat agent: one message in, at most one reply out.

    message -> level 0 (code, free) -> gate (cheap model, only when needed) -> responder loop

A message addressed to the bot, or sent while it is in a live exchange, skips the gate. Anything
else must pass the gate. If the gate or the budget fails the bot stays quiet instead of guessing:
silence costs nothing. Background `maintenance()` summarises long conversations, closes idle
ones and turns recent messages into stored facts.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from marione.agent import prompt
from marione.agent.loop import run_agent
from marione.agent.prefilter import Level0, classify
from marione.agent.profiler import parse_facts
from marione.agent.prompt import ChatContext, Line
from marione.agent.sessions import Session, SessionManager
from marione.agent.tools import ToolContext, ToolRegistry, chat_registry
from marione.agent.types import ChatMessage, MemberDirectory, Reply, WorldView
from marione.db.chatlog import ChatLog
from marione.db.ledger import Ledger
from marione.db.memory import MemoryRepo
from marione.db.settings import SettingsRepo
from marione.domain.roles import tier_for
from marione.domain.rules import AgentRules
from marione.domain.triggers import strip_speaker_prefix
from marione.labels import describe
from marione.llm.types import LLMClient, LLMError

logger = logging.getLogger("marione.agent")

EXHAUSTED_REPLY = "Scusate, sono a corto di Marioncelli mentali. 🧠💸 Ripassate."


class Clock(Protocol):
    def mono(self) -> float: ...
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class AgentConfig:
    model: str
    gate_model: str
    fallbacks: list[str] = field(default_factory=list)
    noise_min_chars: int = 3
    followup_seconds: float = 90
    followup_max_msgs: int = 3
    gate_context_lines: int = 6
    context_users_cap: int = 6
    context_episodes: int = 4
    compact_at: int = 30
    compact_keep: int = 16
    compact_tokens: int = 4500
    hard_window: int = 80
    idle_seconds: float = 1800
    episode_min_chars: int = 40
    responder_max_tokens: int = 280
    gate_max_tokens: int = 20
    summary_max_tokens: int = 320
    facts_max_tokens: int = 400
    temperature: float = 0.85
    profile_msg_threshold: int = 12
    profile_interval_seconds: float = 1800
    profile_batch: int = 3
    observations_per_member: int = 40
    max_reply_chars: int = 1900
    hydrate_lines: int = 30  # lines reloaded from the database when a channel wakes up
    events_in_context: int = 5
    log_trim_seconds: float = 3600


@dataclass
class _Observation:
    name: str
    lines: list[str] = field(default_factory=list)
    last_profiled: float = 0.0


class ChatAgent:
    def __init__(
        self,
        *,
        llm: LLMClient,
        ledger: Ledger,
        memory: MemoryRepo,
        settings: SettingsRepo,
        directory: MemberDirectory,
        config: AgentConfig,
        bot_id: int,
        bot_name: Callable[[], str],
        clock: Clock,
        rules: AgentRules | None = None,
        registry: ToolRegistry | None = None,
        chatlog: ChatLog | None = None,
        world: WorldView | None = None,
    ) -> None:
        self._llm = llm
        self._ledger = ledger
        self._memory = memory
        self._settings = settings
        self._directory = directory
        self._cfg = config
        self._bot_id = bot_id
        self._bot_name = bot_name
        self._clock = clock
        self._rules = rules or AgentRules()
        self._registry = registry or chat_registry()
        self._sessions = SessionManager()
        self._observations: dict[int, _Observation] = {}
        self._known_names: dict[int, str] = {}
        self._chatlog = chatlog
        self._world = world
        self._last_trim = 0.0

    async def _main_model(self) -> str:
        """The model an admin picked on the web page, else the configured default."""
        chosen, _ = await self._settings.ai_models()
        return chosen or self._cfg.model

    async def _gate_model(self) -> str:
        _, chosen = await self._settings.ai_models()
        return chosen or self._cfg.gate_model

    # --- the message path ------------------------------------------------------------------------

    async def handle(self, msg: ChatMessage) -> Reply | None:
        level = classify(msg, min_chars=self._cfg.noise_min_chars)
        if level is Level0.DISCARD:
            return None
        if not await self._settings.is_enabled("agent"):
            return None

        now = self._clock.mono()
        session = await self._session_for(msg.channel_id, now)
        text = self._with_attachments(msg)
        session.add(Line(msg.author_id, msg.author_name, text), now)
        session.trim_hard(self._cfg.hard_window)
        await self._note_member(msg)
        await self._log(msg.channel_id, msg.message_id, msg.author_id, msg.author_name, text, msg)

        expect_reply = level is Level0.ADDRESSED or session.in_followup(
            now, self._cfg.followup_seconds, self._cfg.followup_max_msgs
        )
        if not expect_reply and not await self._gate(msg, session):
            return None
        try:
            reply = await self._respond(msg, session, expect_reply)
        except LLMError as exc:
            logger.warning("the model could not answer: %s", exc)
            # Never mutely dead when spoken to.
            return Reply(EXHAUSTED_REPLY) if msg.addressed else None
        if reply is not None and reply.text:
            session.add(Line(self._bot_id, self._bot_name(), reply.text), self._clock.mono())
            session.note_bot_reply(self._clock.mono())
            # The bot's own message id is only known once Discord has sent it: a negative id
            # derived from the message it answers keeps the line without colliding with real ones.
            await self._log(
                msg.channel_id, -msg.message_id, self._bot_id, self._bot_name(), reply.text, None
            )
        return reply

    async def _session_for(self, channel_id: int, now: float) -> Session:
        """The live window of a channel; after a restart it is reloaded from the database."""
        session = self._sessions.find(channel_id)
        if session is not None:
            return session
        session = self._sessions.get(channel_id, now)
        if self._chatlog is not None:
            for line in await self._chatlog.recent(channel_id, self._cfg.hydrate_lines):
                session.window.append(Line(line.author_id, line.author_name, line.content))
        return session

    async def _log(
        self,
        channel_id: int,
        message_id: int,
        author_id: int,
        author_name: str,
        text: str,
        msg: ChatMessage | None,
    ) -> None:
        if self._chatlog is None:
            return
        await self._chatlog.append(
            channel_id,
            message_id,
            author_id,
            author_name,
            text,
            is_bot=msg is None,
            reply_to_message_id=msg.reply_to_message_id if msg else None,
        )

    @staticmethod
    def _with_attachments(msg: ChatMessage) -> str:
        if not msg.attachments:
            return msg.content
        shown = ", ".join(msg.attachments)
        return f"{msg.content} [attached: {shown}]".strip()

    async def _note_member(self, msg: ChatMessage) -> None:
        if self._known_names.get(msg.author_id) != msg.author_name:
            await self._ledger.remember_name(msg.author_id, msg.author_name)
            self._known_names[msg.author_id] = msg.author_name
        obs = self._observations.setdefault(msg.author_id, _Observation(msg.author_name))
        obs.name = msg.author_name
        obs.lines.append(msg.content[:300])
        del obs.lines[: -self._cfg.observations_per_member]

    async def _gate(self, msg: ChatMessage, session: Session) -> bool:
        recent = [
            f"{self._bot_name() if m.author_id == self._bot_id else m.author}: {m.text}"
            for m in session.history()[-self._cfg.gate_context_lines :]
        ]
        messages = prompt.build_gate(recent, f"{msg.author_name}: {msg.content}")
        try:
            response = await self._llm.complete(
                role="gate",
                model=await self._gate_model(),
                messages=messages,
                max_tokens=self._cfg.gate_max_tokens,
                temperature=0,
                json_mode=True,
                fallbacks=self._cfg.fallbacks,
            )
        except LLMError as exc:
            logger.info("gate unavailable, staying quiet: %s", exc)
            return False
        return prompt.parse_gate(response.text) is True

    async def _respond(
        self, msg: ChatMessage, session: Session, expect_reply: bool
    ) -> Reply | None:
        economy_on = await self._settings.is_enabled("economy")
        context = await self._context(msg, session)
        messages = prompt.build_messages(
            economy_on=economy_on,
            context=context,
            history=session.history(),
            bot_id=self._bot_id,
            current=self._current_line(msg),
            expect_reply=expect_reply,
        )
        ctx = ToolContext(
            ledger=self._ledger,
            directory=self._directory,
            bot_id=self._bot_id,
            now=self._clock.now,
            rules=self._rules,
            economy_enabled=economy_on,
            audit={
                "source": "agent",
                "channel_id": msg.channel_id,
                "message_id": msg.message_id,
                "author_id": msg.author_id,
            },
        )
        result = await run_agent(
            llm=self._llm,
            role="responder",
            model=await self._main_model(),
            fallbacks=self._cfg.fallbacks,
            messages=messages,
            registry=self._registry,
            ctx=ctx,
            max_tokens=self._cfg.responder_max_tokens,
            temperature=self._cfg.temperature,
        )
        if result.silent:
            return None
        text = self._clean(result.text)
        if not text and not result.actions:
            return None
        return Reply(text, result.actions)

    def _current_line(self, msg: ChatMessage) -> str:
        text = self._with_attachments(msg)
        target = msg.reply_author or self._known_names.get(msg.reply_to_id or 0)
        if target and msg.reply_text:
            quoted = msg.reply_text.replace("\n", " ")[:200]
            return f'{msg.author_name} (replying to {target}: "{quoted}"): {text}'
        if target:
            return f"{msg.author_name} (replying to {target}): {text}"
        return f"{msg.author_name}: {text}"

    def _clean(self, text: str | None) -> str | None:
        if not text:
            return None
        names = {"marione", self._bot_name().lower()}
        cleaned = strip_speaker_prefix(text, names).strip()
        return cleaned[: self._cfg.max_reply_chars] or None

    async def _context(self, msg: ChatMessage, session: Session) -> ChatContext:
        involved = [msg.author_id]
        for uid in (msg.reply_to_id, *msg.mentioned_ids):
            if uid and uid not in involved and uid != self._bot_id:
                involved.append(uid)
        involved = involved[: self._cfg.context_users_cap]
        names = {u: await self._ledger.name_of(u, str(u)) for u in involved}
        facts = await self._memory.facts_for(involved)
        episodes = await self._memory.episodes_for(involved, self._cfg.context_episodes)
        balances = [(names[u], await self._ledger.balance(u)) for u in involved]
        tiers: dict[str, str] = {}
        for uid, (name, balance) in zip(involved, balances, strict=True):
            rank, total = await self._ledger.rank_of(uid)
            place = f", #{rank} of {total}" if rank else ""
            tiers[name] = f"{tier_for(balance).name}{place}"
        return ChatContext(
            summary=await self._memory.summary(msg.channel_id),
            balances=balances,
            facts=[(names[u], facts[u]) for u in involved if u in facts],
            episodes=[e.text for e in episodes],
            tiers=tiers,
            events=await self._events(involved),
            world=self._world.snapshot(msg.channel_id) if self._world is not None else None,
        )

    async def _events(self, involved: list[int]) -> list[str]:
        entries = await self._ledger.recent_events(involved, self._cfg.events_in_context)
        lines: list[str] = []
        for e in reversed(entries):
            who = await self._ledger.name_of(e.user_id, str(e.user_id))
            other = await self._ledger.name_of(e.counterparty, "") if e.counterparty else None
            lines.append(f"{who}: {describe(e.reason, other)} ({e.delta:+d})")
        return lines

    # --- background work -------------------------------------------------------------------------

    async def maintenance(self) -> None:
        """Run about once a minute: summarise, close idle conversations, learn about members."""
        if not await self._settings.is_enabled("agent"):
            return
        now = self._clock.mono()
        if self._chatlog is not None and now - self._last_trim >= self._cfg.log_trim_seconds:
            self._last_trim = now
            await self._chatlog.trim()
        for session in self._sessions.all():
            if session.is_idle(now, self._cfg.idle_seconds):
                await self._close(session)
            elif session.needs_compaction(self._cfg.compact_at, self._cfg.compact_tokens):
                await self._compact(session)
        await self._learn(now)

    async def _close(self, session: Session) -> None:
        summary = await self._memory.summary(session.channel_id)
        if len(summary) >= self._cfg.episode_min_chars:
            await self._memory.add_episode(session.participants(), summary)
        await self._memory.set_summary(session.channel_id, "")
        self._sessions.close(session.channel_id)

    async def _compact(self, session: Session) -> None:
        old = session.old_for_compaction(self._cfg.compact_keep)
        if not old:
            return
        session.compacting = True
        try:
            current = await self._memory.summary(session.channel_id)
            response = await self._llm.complete(
                role="compressor",
                model=await self._gate_model(),
                messages=prompt.build_compress(current, [f"{m.author}: {m.text}" for m in old]),
                max_tokens=self._cfg.summary_max_tokens,
                temperature=0.3,
                fallbacks=self._cfg.fallbacks,
            )
            if response.text and response.text.strip():
                await self._memory.set_summary(session.channel_id, response.text.strip())
                session.apply_compaction(len(old))
        except LLMError as exc:
            logger.info("could not summarise (will retry): %s", exc)
        finally:
            session.compacting = False

    async def _learn(self, now: float) -> None:
        due = sorted(
            (
                (obs.last_profiled, uid)
                for uid, obs in self._observations.items()
                if len(obs.lines) >= self._cfg.profile_msg_threshold
                and now - obs.last_profiled >= self._cfg.profile_interval_seconds
            )
        )
        for _, uid in due[: self._cfg.profile_batch]:
            obs = self._observations[uid]
            known = (await self._memory.facts_for([uid])).get(uid, [])
            try:
                response = await self._llm.complete(
                    role="profiler",
                    model=await self._gate_model(),
                    messages=prompt.build_facts(obs.name, known, obs.lines),
                    max_tokens=self._cfg.facts_max_tokens,
                    temperature=0.2,
                    json_mode=True,
                    fallbacks=self._cfg.fallbacks,
                )
            except LLMError as exc:
                logger.info("could not update memories (will retry): %s", exc)
                return  # model unavailable: postpone everyone, nothing is lost
            for fact in parse_facts(response.text):
                await self._memory.add_fact(uid, fact)
            obs.lines.clear()
            obs.last_profiled = now

    async def forget(self, user_id: int) -> int:
        """A member asks to be forgotten: stored facts and pending observations."""
        self._observations.pop(user_id, None)
        count = await self._memory.forget_member(user_id)
        for session in self._sessions.all():
            session.window = [m for m in session.window if m.author_id != user_id]
        return count
