"""Level 0: decide from the message alone, with no model, whether it can matter at all.

This protects the budget: noise, commands and bare links never cost a single token.
"""

from enum import StrEnum

from marione.agent.types import ChatMessage


class Level0(StrEnum):
    DISCARD = "discard"
    ADDRESSED = "addressed"
    GATE = "gate"


def classify(msg: ChatMessage, *, min_chars: int = 3) -> Level0:
    if msg.is_bot:
        return Level0.DISCARD
    if msg.addressed:  # being addressed always gets through
        return Level0.ADDRESSED
    text = msg.content.strip()
    if len(text) < min_chars:
        return Level0.DISCARD
    if text[0] in "!/":  # a bot command
        return Level0.DISCARD
    if text.lower().startswith(("http://", "https://")) and " " not in text:
        return Level0.DISCARD  # a bare link
    if not any(c.isalnum() for c in text):
        return Level0.DISCARD  # only emoji or punctuation
    return Level0.GATE
