import re
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from marione.domain.afk import VoiceFlags, is_away, is_due
from marione.domain.guardrails import check_agent_action
from marione.domain.rules import AgentRules, EconomyRules
from marione.domain.spam import SpamTracker, Verdict, spam_fine
from marione.domain.triggers import compile_trigger, is_called, strip_speaker_prefix

RULES = EconomyRules()


class TestSpamTracker:
    def test_substantial_message_earns_then_cooldown(self) -> None:
        t = SpamTracker(RULES)
        assert t.register(1, "ciao a tutti", 0) == Verdict.EARN
        assert t.register(1, "come va oggi", 5) == Verdict.IGNORE
        assert t.register(1, "tutto bene qui", 25) == Verdict.EARN

    def test_short_message_is_ignored(self) -> None:
        assert SpamTracker(RULES).register(1, "ok", 0) == Verdict.IGNORE

    def test_burst_is_penalised_once_per_cooldown(self) -> None:
        t = SpamTracker(RULES)
        verdicts = [t.register(1, f"messaggio {i}", i * 0.1) for i in range(12)]
        assert verdicts.count(Verdict.SPAM) == 1

    def test_repeating_the_same_message_is_spam(self) -> None:
        t = SpamTracker(RULES)
        out = [t.register(1, "uguale", i * 30) for i in range(3)]
        assert out[-1] == Verdict.SPAM

    def test_members_are_independent(self) -> None:
        t = SpamTracker(RULES)
        assert t.register(1, "messaggio uno", 0) == Verdict.EARN
        assert t.register(2, "messaggio due", 1) == Verdict.EARN

    def test_penalty_after_cooldown_applies_again(self) -> None:
        t = SpamTracker(RULES)
        for i in range(8):
            t.register(1, f"spam {i}", i * 0.1)
        later = [t.register(1, f"altro {i}", 100 + i * 0.1) for i in range(8)]
        assert Verdict.SPAM in later


def test_spam_fine_uses_percentage_with_minimum_and_never_exceeds_balance() -> None:
    assert spam_fine(10_000, RULES) == 1_000
    assert spam_fine(100, RULES) == 50
    assert spam_fine(20, RULES) == 20
    assert spam_fine(0, RULES) == 0


class TestGuardrails:
    NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def check(self, **kw: object) -> object:
        args: dict[str, object] = {
            "amount": 50,
            "target_id": 10,
            "bot_id": 99,
            "now": self.NOW,
            "last_action_at": None,
            "rules": AgentRules(),
        }
        args.update(kw)
        return check_agent_action(**args)  # type: ignore[arg-type]

    def test_allows_a_normal_action(self) -> None:
        d = self.check()
        assert d.allowed and d.amount == 50  # type: ignore[attr-defined]

    def test_caps_the_amount(self) -> None:
        assert self.check(amount=9999).amount == 200  # type: ignore[attr-defined]

    def test_refuses_non_positive(self) -> None:
        assert not self.check(amount=0).allowed  # type: ignore[attr-defined]
        assert not self.check(amount=-5).allowed  # type: ignore[attr-defined]

    def test_refuses_acting_on_itself(self) -> None:
        assert not self.check(target_id=99).allowed  # type: ignore[attr-defined]

    def test_cooldown_per_member(self) -> None:
        recent = self.NOW - timedelta(seconds=60)
        old = self.NOW - timedelta(seconds=600)
        assert not self.check(last_action_at=recent).allowed  # type: ignore[attr-defined]
        assert self.check(last_action_at=old).allowed  # type: ignore[attr-defined]


class TestTriggers:
    PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        compile_trigger("marione"),
        compile_trigger("marioncelli"),
    ]

    def test_plain_and_case(self) -> None:
        assert is_called("Ehi MARIONE", self.PATTERNS)

    def test_leet_and_spacing(self) -> None:
        assert is_called("m4r10n3 dove sei", self.PATTERNS)
        assert is_called("m a r i o n e", self.PATTERNS)
        assert is_called("m.a.r.i.o.n.e", self.PATTERNS)

    def test_unrelated_text(self) -> None:
        assert not is_called("buongiorno a tutti", self.PATTERNS)

    def test_strip_speaker_prefix(self) -> None:
        names = ["marione"]
        assert strip_speaker_prefix("Marione: ciao", names) == "ciao"
        assert strip_speaker_prefix("marione: marione: ciao", names) == "ciao"
        assert strip_speaker_prefix("marionette sono io", names) == "marionette sono io"
        assert strip_speaker_prefix("ciao", names) == "ciao"


class TestAfk:
    def test_away_when_headphones_or_mic_off(self) -> None:
        assert not is_away(VoiceFlags())
        assert is_away(VoiceFlags(self_deaf=True))
        assert is_away(VoiceFlags(self_mute=True))
        assert is_away(VoiceFlags(mute=True))

    def test_due_after_threshold(self) -> None:
        assert not is_due(None, 1000, 300)
        assert not is_due(800, 1000, 300)
        assert is_due(600, 1000, 300)
        assert not is_due(0, 1000, 0)  # 0 disables the feature
