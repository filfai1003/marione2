# Marione — note per chi lavora sul codice

- Un solo comando di verifica: `bash scripts/check.sh` (ruff, ruff format, mypy strict, pytest). Deve essere verde prima di ogni commit.
- Logica pura in `domain/` (nessun import di discord/asyncpg, il tempo è sempre passato come argomento). `services/` orchestra, `db/` parla con Postgres, `bot/` è solo l'adattatore Discord.
- Le regole di sicurezza vivono due volte: nel codice (`domain/guardrails.py`) e nel DB (vincoli, funzioni `apply_delta`/`move`). Non indebolire una sola delle due.
- Il saldo non si scrive mai direttamente: solo tramite le funzioni SQL. `marione.balance_audit` deve restare vuota (c'è un test).
- Ogni effetto ripetibile ha una chiave di idempotenza (messaggio, minuto vocale, annullamento).
- L'LLM passa solo da `LLMClient`; nei test si usa `tests/fakes.ScriptedLLM`. Il costo è quello reale riportato da OpenRouter.
- Niente `except Exception` (ruff BLE). Migrazioni: solo nuovi file `migrations/NNNN_*.sql`, mai modificare quelli applicati.
- Python 3.12 fisso (l'audio di discord.py richiede `audioop`).
- Non fare deploy né toccare il Postgres di produzione senza chiederlo all'utente.
