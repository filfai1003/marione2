# Web API (contratto tra `src/marione/web/site/` e il server)

Tutte le risposte sono JSON. Autenticazione: cookie di sessione firmato (`marione_session`, httponly), impostato dal login Discord (`/auth/login` → Discord → `/auth/callback` → `/`). Il client usa sempre `credentials: 'same-origin'`.

Errori: HTTP 4xx/5xx con corpo `{"ok": false, "error": "<codice>", "message": "<testo italiano mostrabile>"}`.
Codici: `unauthorized` (401), `not_in_guild` (403), `forbidden` (403, serve admin), `bad_request` (400), `feature_off` (409), `not_in_voice` (409), `cooldown` (429, con `cooldownSeconds`), `insufficient` (409), `not_found` (404), `too_large` (413), `invalid_audio` (422), `limit` (409), `exists` (409, nome già usato), `busy` (409, il bot sta suonando altrove), `error` (502, riproduzione non riuscita).

Importi sempre interi (Marioncelli). Id Discord sempre **stringhe**.

## Identità

`GET /api/me`

```json
{"configured": true, "loggedIn": false}
```
oppure, con sessione valida e membro del server:
```json
{"configured": true, "loggedIn": true, "inGuild": true,
 "id": "123", "name": "Giulia", "handle": "giulia_92", "avatar": "https://…|null",
 "isAdmin": false, "inVoice": true, "voiceChannel": "general"}
```
`configured:false` = login non configurato (in locale/preview la sessione è già aperta, quindi non succede). `inGuild:false` = utente loggato ma non nel server.

`POST /auth/logout` (anche GET) → redirect a `/`. `GET /auth/login` → redirect a Discord.

## Stato completo (poll ogni ~15 s e dopo ogni azione)

`GET /api/state` (richiede login + membro del server)

```json
{
 "ok": true,
 "me": {"id":"1","name":"Giulia","handle":"giulia_92","avatar":null,"isAdmin":false},
 "balance": 3450,
 "tier": {"key":"cameriere","name":"Cameriere","emoji":"🧑‍🍳","color":"#1ABC9C","min":1000,
          "next": {"name":"Portafoglio gonfio","min":10000,"missing":6550} },
 "rank": 7, "memberCount": 128,
 "leaderboard": [{"id":"2","name":"Nonna Pina","avatar":null,"bal":356900,
                  "tier":{"name":"Re della pastasciutta","emoji":"👑","color":"#9B59B6"},
                  "isMe": false}],
 "members": [{"id":"2","name":"Nonna Pina","avatar":null,"bal":356900}],
 "history": [{"id": 991, "delta": -50, "reason": "transfer_out",
              "label": "Mandati a Marcello", "with": "Marcello", "at": "2026-10-16T21:03:11Z"}],
 "sounds": [{"id":"7","name":"Applausi","emoji":"👏","durationMs":1800,"fav":true,"own":false}],
 "soundboardVolume": 80,
 "entrances": [{"name":"Squillo di tromba","size":48211,"durationMs":2100}],
 "entranceLimit": 10,
 "modules": {"economy":true,"sound":true,"soundboard":true,"roles":false,"rob":true,"agent":true},
 "roles": [{"name":"Morto di fame","min":0,"color":"#95A5A6","emoji":"🥀"}],
 "rob": {"cooldownSeconds": 0, "minAmount": 1},
 "inVoice": true, "voiceChannel": "general"
}
```
`members` = tutti gli altri membri umani con almeno una riga in `balances` (target di pagamenti/furti), ordinati per nome. `history` = ultime 30 righe dell'utente, dalla più recente. `tier.next` è `null` al livello massimo. `leaderboard` = top 50.

`GET /api/live` → `{"ok":true,"balance":3450,"inVoice":true,"voiceChannel":"general","robCooldownSeconds":0}` (poll leggero ogni ~5 s).

## Economia

`POST /api/economy/pay` `{"memberId":"2","amount":100}` → `{"ok":true,"balance":3350,"message":"Hai mandato 100 Marioncelli a Marcello."}`
Errori: `insufficient`, `bad_request` (importo ≤ 0, se stessi, bot), `feature_off`.

`GET /api/economy/rob-preview?victimId=2&amount=500` → `{"ok":true,"prob":0.31,"fine":120,"cooldownSeconds":0}` (`prob` in 0..1, stessa formula del furto vero).

`POST /api/economy/rob` `{"victimId":"2","amount":500}` →
```json
{"ok":true,"success":true,"amount":500,"fine":0,"balance":3950,"cooldownSeconds":3600,
 "message":"Giulia ha svaligiato Marcello di 500 Marioncelli!"}
```
Errori: `cooldown` (con `cooldownSeconds`), `insufficient` (la vittima non ha abbastanza), `bad_request`, `feature_off`. Un furto fallito risponde `ok:true,success:false` con `fine` > 0.

## Soundboard (libreria condivisa del server)

`GET /api/soundboard/list` → `{"ok":true,"sounds":[…come in state…],"volume":80}` (preferiti per primi, poi per nome).
`GET /api/soundboard/audio?id=7` → il file audio (per l'anteprima nel browser).
`POST /api/soundboard/play` `{"id":"7"}` → `{"ok":true}`; errore `not_in_voice` se l'utente non è in un canale vocale.
`POST /api/soundboard/stop` `{}` → `{"ok":true}`.
`POST /api/soundboard/volume` `{"percent":80}` (0–100) → `{"ok":true,"volume":80}`.
`POST /api/soundboard/favorite` `{"id":"7"}` → `{"ok":true,"fav":true}` (toggle).
`POST /api/soundboard/add` multipart: `name` (1–40 caratteri), `emoji` (opzionale, un carattere/emoji), `file` (mp3/wav/ogg, ≤ 8 MB, ≤ 30 s) → `{"ok":true,"sound":{…}}`.
`POST /api/soundboard/rename` `{"id":"7","name":"Nuovo","emoji":"🎺"}` (emoji opzionale) — solo il creatore o un admin.
`POST /api/soundboard/remove` `{"id":"7"}` — solo il creatore o un admin.

## Suoni d'entrata (personali: ne suona uno a caso quando entri in vocale)

`GET /api/entrance/list` → `{"ok":true,"entrances":[{"name","size","durationMs"}],"limit":10}`
`GET /api/entrance/audio?name=Squillo` → il file audio.
`POST /api/entrance/add` multipart: `name`, `file` (mp3/wav/ogg, ≤ 8 MB, ≤ 15 s) → `{"ok":true}`; errore `limit` oltre 10.
`POST /api/entrance/remove` `{"name":"Squillo"}` → `{"ok":true}`.

## Admin (solo amministratori del server)

`POST /api/admin/balance` `{"memberId":"2","action":"give|take|set","amount":500,"reason":"…"}` → `{"ok":true,"balance":1500}`.
`POST /api/admin/feature` `{"key":"roles","on":true}` → `{"ok":true,"modules":{…}}` (chiavi: economy, sound, soundboard, roles, rob, agent).
`GET /api/admin/usage` → `{"ok":true,"aiEnabled":true,"todayUsd":0.0123,"monthUsd":0.41,"dailyBudgetUsd":0.5,"monthlyBudgetUsd":10.0,"byModel":[{"model":"…","calls":12,"costUsd":0.01}]}`.

## Statici

`GET /` → `index.html` (SPA), `GET /health` → 200/503 (usato da Railway).
