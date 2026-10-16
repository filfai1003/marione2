# Marione

Il bot Discord che tiene vivo il server. Python 3.12 · discord.py · Postgres (schema `marione`) ·
OpenRouter. Tutti i dati vivono nel suo database: niente è salvato nei messaggi di Discord.

## Funzioni

| Funzione | Cosa fa |
|---|---|
| Economia | Marioncelli per messaggi e minuti in vocale, `/marione paga`, classifica. Il saldo è la somma di un registro che non si modifica mai (vista di controllo sempre vuota). |
| Ruoli ricchezza | 12 ruoli (da *Morto di fame* a *Divinità Spaghettara*) assegnati in base al saldo. Creati e gestiti solo da Marione. **Spenti di default**: li accende un admin. |
| Furto | `/marione deruba`: probabilità e multa calcolate in modo che tentare sia sempre in perdita; se ti beccano paghi la multa alla vittima. Un tentativo l'ora, il tempo è nel database. |
| Soundboard | Libreria di suoni condivisa: tutti aggiungono (sito o `/marione soundboard-add`) e suonano nella propria vocale; solo gli admin eliminano. |
| Presenza in vocale | Marione entra appena qualcuno entra in vocale e resta finché non rimane solo. |
| Suoni d'entrata | Quando entri in vocale suona uno dei tuoi audio a caso. Li gestiscono solo gli admin (dal sito o con `/marione-admin entrance-*`). |
| Chat con l'AI | Risponde se chiamato o quando ha qualcosa da dire (OpenRouter). Vede cosa stai citando, chi è in vocale, il tuo ruolo e i movimenti recenti; ricorda i membri in modo strutturato; la conversazione sopravvive ai riavvii. Può regalare o multare monete con tetti rigidi. |
| Sito web | Login con Discord, in inglese, italiano o francese. Per tutti: saldo, classifica e movimenti (paginati), pagamenti, furto, soundboard con ricerca e filtri. Solo admin: suoni d'entrata di tutti i membri, "cervello di Marione" (prompt di sistema, appunti e ricordi su ogni membro, chat salvata per canale), funzioni, saldi, scelta del modello AI e costi. |
| Lingue | Inglese (predefinito), italiano, francese: sito, risposte del bot e nomi dei comandi Discord (tradotti in base alla lingua dell'app Discord). Ognuno sceglie con `/marione language` o dal sito; l'admin sceglie la lingua degli annunci pubblici. |

Comandi (nomi inglesi, mostrati in italiano/francese a chi ha Discord in quella lingua):
`/marione` balance, pay, rob, leaderboard, history, soundboard, soundboard-add, language, forget ·
`/marione-admin` give, fine, set, undo, feature, status, server-language, entrance-add/list/remove,
soundboard-remove, import-old.

## Sviluppo

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
bash scripts/check.sh                 # ruff + mypy strict + pytest
.venv/bin/python -m marione.dev.preview   # il sito con dati d'esempio su http://127.0.0.1:8099
```

I test avviano un Postgres temporaneo (o usano `TEST_DATABASE_URL`). L'anteprima non tocca Discord:
usa un finto server e un Postgres temporaneo (servono i binari di PostgreSQL). L'LLM nei test è
sempre un finto LLM con copione.

## Configurazione

Vedi `.env.example`. Obbligatorie: `DISCORD_TOKEN`, `GUILD_ID`, `DATABASE_URL`. L'AI parte con
`OPENROUTER_API_KEY`; il login del sito con `PUBLIC_URL`, `DISCORD_CLIENT_ID`,
`DISCORD_CLIENT_SECRET`, `WEB_SESSION_SECRET`.

## Pubblicazione (Railway)

1. Servizio nello stesso progetto del Postgres, `DATABASE_URL` sulla rete privata; il `Dockerfile` e
   `railway.toml` sono pronti. Le migrazioni girano all'avvio (lock consultivo, una transazione per
   file) e `/health` risponde 200/503.
2. Discord Developer Portal → bot: attiva gli intent **Server Members** e **Message Content**.
   Permessi: Connect, Speak, Manage Roles (per i ruoli ricchezza), Send Messages.
3. Discord → OAuth2: aggiungi `https://<tuo-dominio>/auth/callback` ai redirect.
4. Il ruolo di Marione deve stare **sopra** i ruoli ricchezza nella lista dei ruoli del server.
5. Il sito e il bot sono lo stesso processo, sulla stessa porta.

Vedi `docs/DECISIONS.md` per le scelte di progetto e `docs/WEB_API.md` per il contratto del sito.
