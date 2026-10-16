"""Text helpers for the chat agent: call-out detection and cleaning of model output."""

import re
from collections.abc import Iterable

# Look-alike characters per letter, so "marione" is also caught as "m4r10n3" or "m4r!0ne".
_LEET = {
    "a": "a4@",
    "b": "b8",
    "c": "c(",
    "e": "e3",
    "g": "g9",
    "i": "i1!|",
    "l": "l1|",
    "o": "o0",
    "s": "s5$",
    "t": "t7+",
    "z": "z2",
}
# Up to 3 separators between letters ("m a r i o n e", "m.a.r.i.o.n.e"). Not letters or digits,
# so the pattern cannot run away.
_SEPARATOR = r"[\s._\-*'\"~:;,]{0,3}"


def _letter(ch: str) -> str:
    return "[" + "".join(re.escape(c) for c in _LEET.get(ch, ch)) + "]"


def compile_trigger(word: str) -> re.Pattern[str]:
    return re.compile(_SEPARATOR.join(_letter(c) for c in word.lower()), re.IGNORECASE)


def is_called(text: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    """True if the text names the bot, even with leet spelling, spacing or mixes."""
    return any(p.search(text) for p in patterns)


def strip_speaker_prefix(text: str, names: Iterable[str]) -> str:
    """Remove a leading "Name:" label the model may have echoed (even repeated)."""
    out = text.lstrip()
    lowered = [n.lower() for n in names if n]
    changed = True
    while changed:
        changed = False
        low = out.lower()
        for name in lowered:
            if low.startswith(name):
                rest = out[len(name) :].lstrip()
                if rest[:1] in (":", "-", "—", ">"):
                    out = rest[1:].lstrip()
                    changed = True
                    break
    return out
