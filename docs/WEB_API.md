# Web API (contratto tra `src/marione/web/site/` e il server)

Tutte le risposte sono JSON. Autenticazione: cookie di sessione firmato (`marione_session`, httponly), impostato dal login Discord (`/auth/login` → Discord → `/auth/callback` → `/`). Il client usa sempre `credentials: 'same-origin'`.

Errori: HTTP 4xx/5xx con corpo `{"ok": false, "error": "<codice>", "message": "<testo già tradotto nella lingua dell'utente>"}`.
Codici: `unauthorized` (401), `not_in_guild` (403), `forbidden` (403, serve admin), `bad_request` (400), `feature_off` (409), `not_in_voice` (409), `cooldown` (429, con `cooldownSeconds`), `insufficient` (409), `not_found` (404), `too_large` (413), `invalid_audio` (422), `limit` (409), `exists` (409, nome già usato), `busy` (409, il bot sta suonando altrove), `error` (502, riproduzione non riuscita).

Importi sempre interi (Marioncelli). Id Discord sempre **stringhe**.

## Lingue

Lingue: `en` (predefinita), `it`, `fr`. Ogni testo che arriva dal server (`message`, `label` dello storico) è già nella lingua dell'utente. La pagina traduce i propri testi.

- La lingua dell'utente è in `GET /api/me` e `GET /api/state` (`"lang": "en"`), insieme a `"languages": ["en","it","fr"]`.
- Se l'utente non ha mai scelto, il server risponde con la lingua scelta dall'admin per il server (predefinita `en`).
- `POST /api/settings/language` `{"lang":"fr"}` → `{"ok":true,"lang":"fr"}`. La preferenza è salvata nel database e vale anche per le risposte del bot su Discord.
- Prima del login (schermata di accesso) la pagina usa la lingua del browser se è una delle tre, altrimenti inglese.

## Identità

`GET /api/me`

```json
{"configured": true, "loggedIn": false, "lang": "en", "languages": ["en","it","fr"]}
```
oppure, con sessione valida e membro del server:
```json
{"configured": true, "loggedIn": true, "inGuild": true,
 "id": "123", "name": "Giulia", "handle": "giulia_92", "avatar": "https://…|null",
 "isAdmin": false, "inVoice": true, "voiceChannel": "general",
 "lang": "it", "languages": ["en","it","fr"]}
```

`POST /auth/logout` (anche GET) → redirect a `/`. `GET /auth/login` → redirect a Discord.

## Stato (poll ogni ~15 s e dopo ogni azione)

`GET /api/state`

```json
{
 "ok": true,
 "lang": "it", "languages": ["en","it","fr"],
 "me": {"id":"1","name":"Giulia","handle":"giulia_92","avatar":null,"isAdmin":false},
 "balance": 3450,
 "tier": {"key":"…","name":"Sbarca il lunario","emoji":"🧑‍🍳","color":"#1ABC9C","min":1000,
          "next": {"name":"Portafoglio gonfio","min":10000,"missing":6550} },
 "rank": 7, "memberCount": 128,
 "leaderboard": [ …le prime 10 righe, come in /api/economy/leaderboard… ],
 "leaderboardTotal": 128,
 "members": [{"id":"2","name":"Nonna Pina","avatar":null,"bal":356900}],
 "history": [ …le ultime 10 righe, come in /api/economy/history… ],
 "historyTotal": 57,
 "sounds": [{"id":"7","name":"Applausi","emoji":"👏","durationMs":1800,"fav":true,"own":false}],
 "soundboardVolume": 80,
 "modules": {"economy":true,"sound":true,"soundboard":true,"roles":false,"rob":true,"agent":true},
 "roles": [{"name":"Morto di fame","min":0,"color":"#95A5A6","emoji":"🥀"}],
 "rob": {"cooldownSeconds": 0, "minAmount": 1},
 "inVoice": true, "voiceChannel": "general"
}
```
I suoni d'entrata non sono più nello stato: sono una pagina solo per admin (sotto).

`GET /api/live` → `{"ok":true,"balance":3450,"inVoice":true,"voiceChannel":"general","robCooldownSeconds":0}`.

## Economia

Liste paginate (mai liste infinite): `offset` (da 0) e `limit` (1–50, predefinito 10).

`GET /api/economy/leaderboard?offset=0&limit=10&q=` → `{"ok":true,"total":128,"items":[{"rank":1,"id":"2","name":"Nonna Pina","avatar":null,"bal":356900,"tier":{"name":"…","emoji":"👑","color":"#9B59B6"},"isMe":false}]}`. `q` filtra per nome (opzionale); `rank` è la posizione vera in classifica anche quando si filtra.

`GET /api/economy/history?offset=0&limit=10` → `{"ok":true,"total":57,"items":[{"id":991,"delta":-50,"reason":"transfer_out","label":"Sent to Marcello","with":"Marcello","at":"2026-10-16T21:03:11Z"}]}` (dalla più recente).

`POST /api/economy/pay` `{"memberId":"2","amount":100}` → `{"ok":true,"balance":3350,"message":"…"}`.

`GET /api/economy/rob-preview?victimId=2&amount=500` → `{"ok":true,"prob":0.31,"fine":120,"cooldownSeconds":0}`.

`POST /api/economy/rob` `{"victimId":"2","amount":500}` → `{"ok":true,"success":true,"amount":500,"fine":0,"balance":3950,"cooldownSeconds":3600,"message":"…"}`.

## Soundboard (libreria condivisa del server)

`GET /api/soundboard/list` → `{"ok":true,"sounds":[…],"volume":80}` (preferiti per primi, poi per nome).
`GET /api/soundboard/audio?id=7` → il file audio (`&download=1` lo manda come allegato col nome del suono; chiunque).
`POST /api/soundboard/play` `{"id":"7"}`; `stop` `{}`; `volume` `{"percent":80}`; `favorite` `{"id":"7"}` (toggle).
**Scorciatoie**: nessuna impostazione. I primi dieci suoni della lista del membro (preferiti per primi, poi per nome) rispondono a Ctrl+1 … Ctrl+9 e Ctrl+0: ogni suono in `sounds` (lista e `/api/state`) ha `"shortcut": "Ctrl+1"|…|"Ctrl+0"|null`, calcolato dal server, quindi i tasti seguono la lista. La pagina li ascolta su ogni pagina e chiama `play`.
`POST /api/soundboard/add` multipart: `name` (1–40), `emoji` (opzionale), `file` (mp3/wav/ogg, ≤ 8 MB, ≤ 30 s). Tutti possono aggiungere.
`POST /api/soundboard/rename` `{"id":"7","name":"Nuovo","emoji":"🎺"}` — solo admin (nome e icona).
`POST /api/soundboard/remove` `{"id":"7"}` — **solo admin** (altrimenti `forbidden`).

## Musica

`GET /api/music/state` → `{"ok":true,"nowPlaying":{"title","url","duration","channel","thumbnail","source","requestedBy","position","paused"}|null,"queue":[{…senza position/paused…}],"lastError":null,"volume":50,"inVoice":true,"recent":[{"title","url","duration","by","at"}]}` (poll ~5 s sulla pagina Musica).
`GET /api/music/search?q=` → `{"ok":true,"results":[{"title","url","duration","channel","thumbnail","source"}]}`: 10 risultati per un titolo, 1 per un link. Errore `error` (502) se le piattaforme rifiutano.
`POST /api/music/play` `{…un risultato…, "now": false}` → `{"ok":true,"status":"playing|queued","position":0,"message":"…"}`; `now:true` la suona subito. Errori: `not_in_voice`, `busy` (musica per altri in un altro canale), `limit` (coda piena), `error`.
`POST /api/music/skip|stop|pause|volume|remove` (`volume`: `{"percent":50}`, `remove`: `{"index":0}`) → stato aggiornato + `message`.

### Link supportati

`/api/music/search?q=<link>` e `/api/music/play` accettano: YouTube, SoundCloud, **Suno** (`suno.com/song/<id>`, `suno.com/s/<codice>`: titolo, artista, copertina e durata vengono dall'API pubblica dei clip di Suno), qualsiasi sito che yt-dlp conosce, un **file audio diretto** (`.mp3 .m4a .ogg .wav .flac …`) e pagine con un player (`og:audio`, `<audio src>`). Gli indirizzi non pubblici (rete interna, `file:`) sono rifiutati.

### Libreria (mp3 caricati, sempre presenti)

Condivisa dal server; ogni brano ha `url: "upload:<id>"` e `source: "upload"` e si suona/accoda/mette in playlist con gli stessi endpoint di una canzone da link (`play` rilegge titolo e durata dal database).
`GET /api/music/library` → `{"ok":true,"tracks":[{"title","url":"upload:3","duration","channel":"<chi l'ha caricato>","thumbnail":null,"source":"upload","own":true,"size":4123456}],"count","usedBytes","maxFiles","maxBytes","maxFileBytes"}` (più recenti prima).
`POST /api/music/library/add` multipart: `name` (titolo, ≤ 200), `file` (mp3/wav/ogg, ≤ 24 MB, ≤ 3 ore) → `{"ok":true,"track":{…}}`. Errori: `too_large` (413), `invalid_audio` (422), `limit` (409, libreria piena: 300 file o 400 MB), `feature_off`.
`POST /api/music/library/rename` `{"id":"3","title":"…"}` e `remove` `{"id":"3"}` — solo chi l'ha caricato o un admin (`forbidden`). Eliminare un brano lo toglie anche dalle playlist.
`GET /api/music/library/audio?id=3` (`&download=1`) → il file.

### Playlist

Tutti le vedono e le suonano; le modifica solo chi le ha create (o un admin, altrimenti `forbidden`). Max 30 per membro, 200 brani l'una; il nome è unico per membro (`exists`).
`GET /api/music/playlists` → `{"ok":true,"playlists":[{"id":"1","name","owner","own","count","duration"}]}` (le proprie prima).
`GET /api/music/playlist?id=1` → `{"ok":true,"playlist":{…},"tracks":[{"itemId":"9","title","url","duration","channel","thumbnail","source"}]}`.
`POST /api/music/playlist/create` `{"name":"Cena","track":{…opzionale…}}` → `{"ok":true,"playlist":{…}}`; `rename` `{"id","name"}`; `delete` `{"id"}`; `add` `{"id","track":{title,url,duration,channel,thumbnail}}` → `{"ok":true,"message"}`; `remove` `{"id","itemId"}`.
`POST /api/music/playlist/play` `{"id":"1","shuffle":false,"replace":false}` mette in coda tutti i brani (`replace` svuota prima la coda, `shuffle` li mescola; quelli che non si riescono a riprodurre sono saltati, la coda tiene 50 brani) → come `music/skip` più `"added"` e `"skipped"`. Errori: `not_in_voice`, `busy`, `limit`, `error`, `bad_request` (vuota).

### Playlist: ordine, copertine, "salva in playlist"

`GET /api/music/playlists` aggiunge a ogni playlist `"covers":[{"thumbnail","url","source"}]` (i primi 4 brani, per la copertina a mosaico); con `?track=<url>` aggiunge anche `"has": true|false` (la playlist contiene già quel brano).
`POST /api/music/playlist/add` accetta anche `{"id","link":"https://…"}` (YouTube, Suno o altro: il server riconosce il brano; risposta con `"title"`).
`POST /api/music/playlist/create` accetta anche `"tracks":[…]` (fino a 50 brani: "salva la coda come playlist").
`POST /api/music/playlist/remove` accetta `{"id","url"}` per togliere ogni copia di un brano (oltre a `{"id","itemId"}`).
`POST /api/music/playlist/move` `{"id","itemId","index"}` sposta un brano (0 = primo); solo chi ha creato la playlist o un admin. I brani nuovi vanno in fondo; `play` rispetta l'ordine.

## Estensione del browser

L'estensione (Chrome/Edge/Brave, MV3; `GET /marione-extension.zip` la genera con l'indirizzo del sito) fa funzionare Ctrl+1…0 su qualunque scheda, e ha 4 comandi (Ctrl+Shift+1…4, i primi quattro suoni) che l'utente può rendere **globali** (`chrome.commands`) per il browser in background. Non usa il cookie: ha un token personale.
`POST /api/ext/token` (cookie) → `{"ok":true,"token":"…"}` (la pagina lo passa all'estensione con `postMessage`; non lo mostra). Valido 365 giorni, firmato.
`POST /api/ext/revoke` (cookie) scollega tutte le estensioni del membro.
`GET /api/ext/config` → `{"ok":true,"me":{"name"},"inVoice","sounds":[{"id","name","emoji","shortcut"}]}` e `POST /api/ext/play` `{"id":"7"}` (come `soundboard/play`): **solo** con `Authorization: Bearer <token>`; questo token non apre nessun altro endpoint. Errori: `unauthorized` (401), `not_in_guild` (403).

## Suoni d'entrata — SOLO ADMIN

Per chi non è admin ogni endpoint qui risponde `403 forbidden` e la pagina "Entrate" non si mostra. L'admin gestisce i suoni di qualunque membro.

`GET /api/entrance/members` → `{"ok":true,"members":[{"id":"2","name":"Nonna Pina","avatar":null,"count":3}],"limit":10}` — tutti i membri umani del server, chi ha suoni per primo, poi per nome.
`GET /api/entrance/list?memberId=2` → `{"ok":true,"memberId":"2","entrances":[{"name","size","durationMs"}],"limit":10}`.
`GET /api/entrance/audio?memberId=2&name=Squillo` → il file audio.
`POST /api/entrance/add` multipart: `memberId`, `name`, `file` (mp3/wav/ogg, ≤ 8 MB, ≤ 15 s) → `{"ok":true}`; `limit` oltre 10, `exists` se il nome c'è già.
`POST /api/entrance/remove` `{"memberId":"2","name":"Squillo"}` → `{"ok":true}`.

## Admin

`POST /api/admin/balance` `{"memberId":"2","action":"give|take|set","amount":500}` → `{"ok":true,"balance":1500}` (vale anche per sé stessi).
`POST /api/admin/feature` `{"key":"roles","on":true}` → `{"ok":true,"modules":{…}}`.
`GET /api/admin/usage` → `{"ok":true,"aiEnabled":true,"todayUsd":0.0123,"monthUsd":0.41,"dailyBudgetUsd":0.5,"monthlyBudgetUsd":10.0,"byModel":[{"model":"…","calls":12,"costUsd":0.01}]}`.

`GET /api/admin/ai` →
```json
{"ok":true,"aiEnabled":true,
 "model":"anthropic/claude-haiku-4.5","gateModel":"google/gemini-2.5-flash-lite",
 "defaultModel":"anthropic/claude-haiku-4.5","defaultGateModel":"google/gemini-2.5-flash-lite",
 "models":[{"id":"anthropic/claude-haiku-4.5","name":"Anthropic: Claude Haiku 4.5",
            "promptPerMillion":1.0,"completionPerMillion":5.0,"context":200000,"tools":true}]}
```
`models` = i modelli OpenRouter che supportano gli strumenti (servono all'agente), ordinati per nome; può essere vuota se OpenRouter non risponde (allora la pagina mostra un campo di testo libero).
`POST /api/admin/ai` `{"model":"openai/gpt-5-mini","gateModel":"google/gemini-2.5-flash-lite"}` (ognuno opzionale; `null` = torna al predefinito) → stessa risposta di GET. Id non validi → `bad_request`.

### Memoria e prompt dell'AI (solo admin: cosa Marione sa e come ragiona)

`GET /api/admin/ai/prompt` → `{"ok":true,"parts":[{"key":"persona","title":"…","text":"…"},{"key":"gate","title":"…","text":"…"},{"key":"summary","title":"…","text":"…"},{"key":"profiler","title":"…","text":"…"}]}` — i prompt di sistema esattamente come li riceve il modello (persona con e senza economia, router, riassunto, profilazione). Solo lettura.

`GET /api/admin/memory/members?q=&offset=0&limit=20` → `{"ok":true,"total":40,"items":[{"id":"2","name":"Nonna Pina","avatar":null,"facts":5,"episodes":2,"messages":31}]}` — membri con dati salvati (chi ne ha di più per primo), filtro per nome.

`GET /api/admin/memory/member?memberId=2` →
```json
{"ok":true,"member":{"id":"2","name":"Nonna Pina","avatar":null},
 "facts":[{"id":11,"category":"likes","text":"pasta al forno","confidence":4,"updatedAt":"…"}],
 "episodes":[{"id":5,"text":"…","at":"…"}],
 "messages":{"total":31,"items":[{"channel":"#general","text":"…","at":"…"}]}}
```
(`messages` = le ultime 20 righe di chat di quel membro che l'AI tiene come contesto; pagina con `&offset=&limit=`.)

Nel dettaglio membro c'è anche `"habits": ["right now: online, playing Minecraft", "usually online 20:00–01:00 (…)", …]` (in inglese, come li vede il modello).

`POST /api/admin/memory/fact/delete` `{"id":11}` → `{"ok":true}`.
`POST /api/admin/memory/forget` `{"memberId":"2"}` → `{"ok":true,"removed":37}` — cancella fatti, episodi e righe di chat di quel membro (come `/marione dimentica`).

`GET /api/admin/memory/channels` → `{"ok":true,"items":[{"id":"10","name":"#general","summary":"…","messages":120,"updatedAt":"…"}]}` — per ogni canale il riassunto della conversazione e quante righe sono salvate.
`GET /api/admin/memory/channel?channelId=10&offset=0&limit=30` → `{"ok":true,"total":120,"items":[{"author":"Giulia","isBot":false,"text":"…","at":"…"}]}` (dalla più recente).

`GET /api/admin/settings` → `{"ok":true,"serverLanguage":"en"}`; `POST /api/admin/settings` `{"serverLanguage":"it"}` → idem. È la lingua degli annunci pubblici del bot e quella predefinita per chi non ha scelto.

## Statici

`GET /` → `index.html` (SPA), `GET /health` → 200/503 (usato da Railway).

## Giochi

Serve l'economia accesa e la funzione `games`. Tutto passa dal registro (`game_bet`, `game_win`, `game_refund`); le poste in gioco sono in `game_escrow` e tornano ai proprietari se il server si riavvia a metà partita.

- `GET /api/games` → `{"games":[{"key","economy":"stake|bets","house":bool,"modes":[{"key","seats","teams"}]}], "tables":[{"id","game","mode","stake","status","seats","free","humans"}] (aperti in attesa + i tuoi), "you", "stats":[{"game","played","won","net"}], "top":[{"userId","name","net"}] (7 giorni), "enabled"}`.
- `POST /api/games/create` `{"game","mode","stake","bots":bool,"options":{"level"|"target"|"hands"}}` → `{"table": vista}`. Con `bots:true` (o modalità da 1 posto) la partita parte subito. Massimo 3 tavoli a testa: il più vecchio giocato da solo coi bot si chiude da sé.
- `POST /api/games/join|leave|start|bot|kick|act` con `{"tableId", …}` (`seat` per join/kick, `action` per act) → `{"table": vista}` (`leave` → `{"ok":true}`). Nei giochi contro il banco, un'azione a round finito fa partire il round successivo.
- `GET /api/games/table?id=…&v=<versione>` → risponde appena la versione cambia (al massimo ~25 s); senza `v` risponde subito.
- Vista del tavolo: `{"id","game","mode","teams","stake","status":"waiting|playing|over|closed","round","version","owner","you":posto|null,"seats":[{"name","bot","auto","userId"}|null],"toAct":[posti],"legal":[azioni],"state":<vista del gioco per te>,"log":[…],"result":{…,"nets":{userId:netto}}|null,"turnLeft":s|null}`. Le forme di `state` e delle azioni sono documentate in ogni motore `src/marione/games/<gioco>.py`.
- Errori: `not_found` 404, `forbidden` 403, `illegal`/`not_your_turn`/`insufficient_funds`/`table_full`… 409, `too_many_tables`/`too_many_yours` 429.
