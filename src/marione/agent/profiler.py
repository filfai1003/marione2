"""Reading the model's list of new facts about a member, defensively."""

import json
from typing import Any

from marione.db.memory import CATEGORIES, MAX_FACT_CHARS, Fact

MAX_NEW_FACTS = 8


def parse_facts(text: str | None) -> list[Fact]:
    """Facts from the model's JSON answer. Each bad item is dropped on its own."""
    if not text:
        return []
    try:
        data: Any = json.loads(text)
    except ValueError:
        return []
    items = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    facts: list[Fact] = []
    for item in items[:MAX_NEW_FACTS]:
        if not isinstance(item, dict):
            continue
        category, body = item.get("category"), item.get("text")
        if category not in CATEGORIES or not isinstance(body, str) or not body.strip():
            continue
        confidence = item.get("confidence", 3)
        if not isinstance(confidence, int) or isinstance(confidence, bool):
            confidence = 3
        facts.append(Fact(str(category), body.strip()[:MAX_FACT_CHARS], min(5, max(1, confidence))))
    return facts
