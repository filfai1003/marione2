"""Readable names for ledger entries (in the reader's language), for Discord and the web page."""

from marione.i18n import M, t


def describe(reason: str, counterparty: str | None = None, lang: str | None = None) -> str:
    key = f"r.{reason}"
    if key not in M:
        return reason
    return t(key, lang, who=counterparty or t("someone", lang))
