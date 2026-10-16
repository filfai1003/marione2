# Marione

Bot Discord che tiene vivo il server: un agente AI (OpenRouter) che partecipa alla chat, un'economia
con registro contabile, un suono d'ingresso nei canali vocali e l'AFK automatico.

Python 3.12 · discord.py · Postgres (schema `marione`) · OpenRouter.

## Funzioni (prima versione)

| Funzione | Cosa fa |
|---|---|
| Agente | Risponde quando chiamato o quando ha qualcosa da dire; può regalare/multare monete (con tetti rigidi), ricorda fatti sui membri e può restare in silenzio. |
| Economia | Monete per messaggi e minuti in vocale; registro append-only, saldo = somma dei movimenti, vista di audit sempre vuota. |
| Suono d'ingresso | Un suono scelto a caso tra quelli caricati dal membro quando entra in vocale. |
| AFK | Chi è muto/sordo troppo a lungo viene spostato in un canale temporaneo e paga un piccolo costo al minuto. |

Comandi: `/marione` (saldo, paga, classifica, storico, suono-aggiungi/lista/rimuovi, dimentica) e
`/marione-admin` (regala, multa, imposta, annulla, funzione, stato).

## Sviluppo

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
bash scripts/check.sh      # ruff + mypy strict + pytest
```

I test avviano un Postgres temporaneo (oppure usa `TEST_DATABASE_URL`) e creano un database per test.
L'LLM nei test è sempre un finto LLM con copione: nessuna chiamata di rete.

## Configurazione

Vedi `.env.example`. Obbligatorie: `DISCORD_TOKEN`, `GUILD_ID`, `DATABASE_URL`, `OPENROUTER_API_KEY`
(senza chiave l'agente è spento, il resto funziona).

## Deploy (Railway)

Servizio nello stesso progetto del Postgres, `DATABASE_URL` sulla rete privata. Le migrazioni girano
all'avvio (lock consultivo, una transazione per file). `/health` risponde 200/503.

Intents: Server Members e Message Content. Permessi: Connect, Speak, Move Members, Mute Members,
Manage Channels.

Vedi `docs/DECISIONS.md` per le scelte di progetto.
