"""Earning and losing coins by chatting, being in voice, or being AFK.

Every money change carries an idempotency key built from the event (the message id, the voice
minute), so Discord delivering an event twice, or a retry after a crash, never pays twice.
"""

from dataclasses import dataclass

from marione.db.ledger import Ledger
from marione.domain.rules import EconomyRules
from marione.domain.spam import SpamTracker, Verdict, spam_fine


@dataclass(frozen=True)
class MessageOutcome:
    verdict: Verdict
    amount: int = 0  # coins earned (EARN) or taken (SPAM)


class EconomyService:
    def __init__(self, ledger: Ledger, rules: EconomyRules) -> None:
        self._ledger = ledger
        self._rules = rules
        self._tracker = SpamTracker(rules)

    async def on_message(
        self, user_id: int, name: str, text: str, *, now: float, message_id: int
    ) -> MessageOutcome:
        verdict = self._tracker.register(user_id, text, now)
        if verdict is Verdict.IGNORE:
            return MessageOutcome(verdict)
        await self._ledger.remember_name(user_id, name)
        if verdict is Verdict.EARN:
            earned = await self._ledger.credit(
                user_id, self._rules.message_reward, "chat_reward", key=f"chat:{message_id}"
            )
            return MessageOutcome(verdict, earned)
        fine = spam_fine(await self._ledger.balance(user_id), self._rules)
        if fine <= 0:
            return MessageOutcome(verdict)
        taken = await self._ledger.debit(user_id, fine, "spam_fine", key=f"spam:{message_id}")
        return MessageOutcome(verdict, taken)

    async def voice_tick(self, user_ids: list[int], minute: int) -> int:
        """Pay everyone active in voice for one minute. Safe to call twice for the same minute."""
        total = 0
        for uid in user_ids:
            total += await self._ledger.credit(
                uid, self._rules.voice_per_minute, "voice_reward", key=f"voice:{uid}:{minute}"
            )
        return total

    async def afk_fine(self, user_id: int, *, key: str) -> int:
        return await self._ledger.debit(user_id, self._rules.afk_fine, "afk_fine", key=key)

    async def afk_drain(self, user_id: int, minutes: int, *, key: str) -> int:
        return await self._ledger.debit(
            user_id, minutes * self._rules.afk_drain_per_minute, "afk_drain", key=key
        )
