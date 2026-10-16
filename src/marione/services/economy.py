"""Earning and losing coins by chatting or being in voice.

Every money change carries an idempotency key built from the event (the message id, the voice
minute), so Discord delivering an event twice, or a retry after a crash, never pays twice.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

from marione.db.heists import HeistRepo
from marione.db.ledger import Ledger
from marione.domain.robbery import Odds, odds
from marione.domain.rules import EconomyRules
from marione.domain.spam import SpamTracker, Verdict, spam_fine


@dataclass(frozen=True)
class MessageOutcome:
    verdict: Verdict
    amount: int = 0  # coins earned (EARN) or taken (SPAM)


@dataclass(frozen=True)
class RobResult:
    # "ok" (stolen) | "caught" (fined) | "cooldown" | "victim_poor" | "too_small" | "broke" | "self"
    status: str
    amount: int = 0  # coins stolen (ok)
    fine: int = 0  # coins paid to the victim (caught)
    probability: float = 0.0
    wait_seconds: int = 0

    @property
    def refused(self) -> bool:
        return self.status not in ("ok", "caught")


class EconomyService:
    def __init__(
        self,
        ledger: Ledger,
        rules: EconomyRules,
        heists: HeistRepo | None = None,
        roll: Callable[[], float] = random.random,
    ) -> None:
        self._ledger = ledger
        self._rules = rules
        self._heists = heists
        self._roll = roll
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

    async def pay(self, sender: int, receiver: int, amount: int, *, key: str) -> bool:
        """A payment between members: all of it or nothing. The key makes a retry pay once."""
        return await self._ledger.pay(sender, receiver, amount, key=key)

    # --- robbery -------------------------------------------------------------------------------

    async def rob_preview(self, attacker: int, victim: int, amount: int) -> Odds:
        """The real odds and fine for this attempt: the same numbers the roll will use."""
        return odds(
            amount,
            await self._ledger.balance(attacker),
            await self._ledger.balance(victim),
            await self._ledger.total_money(),
            self._rules.robbery,
        )

    async def rob_cooldown(self, attacker: int) -> int:
        if self._heists is None:
            return 0
        return await self._heists.cooldown_remaining(attacker, self._rules.robbery.cooldown_seconds)

    async def rob(self, attacker: int, victim: int, amount: int) -> RobResult:
        """One heist attempt. Refusals (cooldown, a victim without the money) cost nothing."""
        rules = self._rules.robbery
        if self._heists is None:  # pragma: no cover - wired in build_services
            raise RuntimeError("robbery needs a HeistRepo")
        if attacker == victim:
            return RobResult("self")
        if amount < rules.min_amount:
            return RobResult("too_small")
        attacker_balance = await self._ledger.balance(attacker)
        if attacker_balance <= 0:
            return RobResult("broke")
        if await self._ledger.balance(victim) < amount:
            return RobResult("victim_poor")
        wait = await self.rob_cooldown(attacker)
        if wait > 0:
            return RobResult("cooldown", wait_seconds=wait)
        chances = await self.rob_preview(attacker, victim, amount)
        success = self._roll() < chances.probability
        result = await self._heists.resolve(
            attacker,
            victim,
            amount,
            success=success,
            fine=chances.fine,
            cooldown_seconds=rules.cooldown_seconds,
        )
        if result.status == "ok":
            return RobResult("ok", amount=result.moved, probability=chances.probability)
        if result.status == "caught":
            return RobResult("caught", fine=result.moved, probability=chances.probability)
        return RobResult(result.status, wait_seconds=result.wait_seconds)
