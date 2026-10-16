# Decisioni

1. **Schema `marione` nel Postgres condiviso di Railway.** Stessa tecnologia di FFT, isolamento per schema, nessun nuovo servizio da pagare.
2. **Niente dati nei messaggi Discord.** Il vecchio bot salvava suoni e impostazioni come messaggi in un canale. Ora tutto è nel database: suoni (bytea, max 8 MB), ruoli creati, impostazioni, chat vista dall'AI.
3. **Registro append-only.** Il saldo è la somma dei movimenti, mantenuta da funzioni SQL; una vista di audit lo verifica. Ogni effetto ripetibile ha una chiave di idempotenza.
4. **Furto deciso nel database.** `resolve_heist` controlla il cooldown (dalla tabella `heists`, quindi un riavvio non lo azzera), muove le monete e registra il tentativo in una transazione. Il tiro lo fa il codice (servono le probabilità); un rifiuto (vittima senza fondi) non consuma il tentativo. La multa va **alla vittima**, così le monete non spariscono. Per ogni importo e saldo tentare è una scommessa in perdita: c'è un test di proprietà.
5. **Ruoli ricchezza spenti di default.** Creano ruoli nel server; Marione tocca solo quelli che ha creato (ids nel DB), al massimo 40 cambi ogni 5 minuti.
6. **Agente con tetti rigidi.** Nessuna UI di approvazione in chat: tetto per azione (200), tetto nel DB (500), cooldown per membro derivato dal DB, meta di audit e `/marione-admin annulla`.
7. **Contesto dell'AI.** Finestra della chat salvata nel DB (si ricarica dopo un riavvio, 7 giorni / 200 righe per canale, cancellabile con `/marione dimentica`); il messaggio citato, gli allegati (solo il nome, il modello non li vede), ora, canale, chi è in vocale, ruolo e posizione in classifica, ultimi movimenti.
8. **Costo in dollari reali.** Budget giornaliero/mensile dal costo che OpenRouter riporta per ogni chiamata, con modelli di ripiego.
9. **Memoria strutturata.** Fatti come righe (categoria, testo, confidenza), non testo libero.
10. **Un solo bot, una sola connessione vocale.** Al posto del vecchio pool di worker; i suoni d'entrata non interrompono un suono in corso, la soundboard sì.
11. **Sito senza build.** HTML/CSS/JS semplici con lo stesso design del vecchio sito; stesso processo del bot. Login Discord (scope `identify`), cookie firmato, controllo `Origin` sulle scritture, CSP restrittiva. Il file audio è riconosciuto dai primi byte, non dal tipo dichiarato.
12. **Anteprima locale.** `marione.dev.preview` usa un finto server Discord (`GuildView`) e un Postgres temporaneo; non legge mai `DATABASE_URL`.
13. **Fuori dall'ambito** (si può aggiungere dopo): AFK automatico, musica, giochi/blackjack, reazioni emoji, ruoli per altre cose.
