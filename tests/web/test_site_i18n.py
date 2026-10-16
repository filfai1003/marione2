"""The page's own texts: every key used exists, in all three languages."""

import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "src" / "marione" / "web" / "site" / "js"
DYNAMIC_PREFIXES = ("nav.", "mod.", "brain.cat.", "brain.prompt.")


def test_every_used_key_is_translated() -> None:
    source = (SITE / "i18n.js").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\s*'([\w.]+)': \[(.*)\],$", source, re.M))
    for key, row in rows.items():
        assert row.count("', '") + row.count("', \"") + row.count("\", '") >= 2, key
    used: set[str] = set()
    for file in [*SITE.glob("*.js"), *SITE.glob("pages/*.js")]:
        if file.name == "i18n.js":
            continue
        used |= set(re.findall(r"\bt\('([\w.]+)'", file.read_text(encoding="utf-8")))
    missing = {k for k in used if k not in rows and not k.endswith(".") and k != ".tile"}
    assert not missing, missing
    for prefix in DYNAMIC_PREFIXES:
        assert any(k.startswith(prefix) for k in rows), prefix
