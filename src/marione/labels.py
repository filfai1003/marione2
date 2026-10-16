"""Italian names for ledger entries, shared by the slash commands and the web page."""

_PLAIN = {
    "chat_reward": "Messaggi in chat",
    "voice_reward": "Tempo in vocale",
    "spam_fine": "Multa antispam",
    "afk_fine": "Multa AFK",
    "afk_drain": "Letto AFK",
    "admin_adjust": "Intervento di un admin",
    "reversal": "Operazione annullata",
    "legacy_import": "Saldo dal vecchio Marione",
}
_WITH = {
    "transfer_out": "Mandati a {who}",
    "transfer_in": "Ricevuti da {who}",
    "rob_out": "Svaligiato da {who}",
    "rob_in": "Svaligiato {who}",
    "rob_fine_out": "Multa per il furto a {who}",
    "rob_fine_in": "Multa pagata da {who}",
    "agent_fine_out": "Multa di {who}",
    "agent_fine_in": "Multa incassata",
    "agent_gift_out": "Regalo a {who}",
    "agent_gift_in": "Regalo di {who}",
}


def describe(reason: str, counterparty: str | None = None) -> str:
    if reason in _PLAIN:
        return _PLAIN[reason]
    template = _WITH.get(reason)
    if template is None:
        return reason
    return template.format(who=counterparty or "qualcuno")
