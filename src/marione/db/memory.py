"""What the agent remembers: structured facts per member, episodes, and session summaries.

Facts are rows with a category, a confidence and dates, not a blob of text the model rewrites.
A fact can be added, corrected or dropped on its own, and a bad model answer can only ever
add a bounded number of short rows.
"""

from dataclasses import dataclass

from marione.db.pool import Pool

CATEGORIES = (
    "identity",
    "likes",
    "dislikes",
    "opinions",
    "personality",
    "humor",
    "relationship",
    "notes",
)
MAX_FACTS_PER_MEMBER = 40
MAX_FACT_CHARS = 300


@dataclass(frozen=True)
class Fact:
    category: str
    text: str
    confidence: int


@dataclass(frozen=True)
class Episode:
    participants: list[int]
    text: str


class MemoryRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    # --- facts ---------------------------------------------------------------------------
    async def add_fact(self, user_id: int, fact: Fact) -> bool:
        """Store a fact. Returns False if it was rejected (unknown category, empty text).

        Saying the same thing again raises its confidence (up to 5) instead of duplicating it.
        When a member passes the limit the weakest, oldest facts are dropped.
        """
        text = " ".join(fact.text.split())[:MAX_FACT_CHARS]
        if fact.category not in CATEGORIES or not text:
            return False
        confidence = min(5, max(1, fact.confidence))
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "insert into marione.members (user_id) values ($1) on conflict do nothing", user_id
            )
            await conn.execute(
                "insert into marione.memory_facts (user_id, category, text, confidence)"
                " values ($1, $2, $3, $4)"
                " on conflict (user_id, category, lower(text)) do update"
                " set confidence = least(5, marione.memory_facts.confidence + 1),"
                " updated_at = now()",
                user_id,
                fact.category,
                text,
                confidence,
            )
            await conn.execute(
                "delete from marione.memory_facts where id in ("
                " select id from marione.memory_facts where user_id = $1"
                " order by confidence desc, updated_at desc offset $2)",
                user_id,
                MAX_FACTS_PER_MEMBER,
            )
        return True

    async def facts_for(self, user_ids: list[int], per_member: int = 8) -> dict[int, list[Fact]]:
        rows = await self._pool.fetch(
            "select user_id, category, text, confidence from ("
            " select *, row_number() over ("
            "  partition by user_id order by confidence desc, updated_at desc) as rn"
            " from marione.memory_facts where user_id = any($1::bigint[])) t where rn <= $2"
            " order by user_id, rn",
            user_ids,
            per_member,
        )
        out: dict[int, list[Fact]] = {}
        for r in rows:
            out.setdefault(r["user_id"], []).append(Fact(r["category"], r["text"], r["confidence"]))
        return out

    async def forget_member(self, user_id: int) -> int:
        """Delete everything remembered about a member (their right to be forgotten)."""
        facts = await self._pool.execute(
            "delete from marione.memory_facts where user_id = $1", user_id
        )
        episodes = await self._pool.execute(
            "delete from marione.episodes where $1 = any(participants)", user_id
        )
        return int(facts.split()[-1]) + int(episodes.split()[-1])

    # --- episodes and summaries ----------------------------------------------------------
    async def add_episode(self, participants: list[int], text: str) -> None:
        text = " ".join(text.split())[:400]
        if text and participants:
            await self._pool.execute(
                "insert into marione.episodes (participants, text) values ($1, $2)",
                participants,
                text,
            )

    async def episodes_for(self, user_ids: list[int], limit: int = 4) -> list[Episode]:
        rows = await self._pool.fetch(
            "select participants, text from marione.episodes where participants && $1::bigint[]"
            " order by id desc limit $2",
            user_ids,
            limit,
        )
        return [Episode(list(r["participants"]), r["text"]) for r in reversed(rows)]

    async def summary(self, channel_id: int) -> str:
        value = await self._pool.fetchval(
            "select summary from marione.session_summaries where channel_id = $1", channel_id
        )
        return str(value or "")

    async def set_summary(self, channel_id: int, summary: str) -> None:
        await self._pool.execute(
            "insert into marione.session_summaries (channel_id, summary) values ($1, $2)"
            " on conflict (channel_id) do update set summary = excluded.summary,"
            " updated_at = now()",
            channel_id,
            summary,
        )
