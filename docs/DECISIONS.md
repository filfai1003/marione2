# Decisioni

1. **Schema `marione` nel Postgres condiviso di Railway.** Stessa tecnologia di FFT, isolamento per schema, nessun nuovo servizio da pagare.
2. **Registro append-only.** Il vecchio bot salvava saldi sovrascrivibili. Ora il saldo è la somma dei movimenti, mantenuta da funzioni SQL; una vista di audit lo verifica.
3. **Agente con tetti rigidi.** Nessuna UI di approvazione in chat: la sicurezza viene da tetto per azione (200), tetto per movimento dell'agente nel DB (500), cooldown per membro derivato dal DB, meta di audit e `/marione-admin annulla`.
4. **Costo in dollari reali.** Budget giornaliero/mensile calcolato sul costo restituito da OpenRouter (`usage.include`), con modelli di ripiego.
5. **Memoria strutturata.** Fatti come righe (categoria, testo, confidenza) invece di testo libero; `/marione dimentica` per la privacy.
6. **Audio in Postgres (bytea, max 8 MB).** Un solo posto da salvare e ripristinare.
7. **Un solo bot** al posto del vecchio pool di worker.
8. **Nome neutro per il canale AFK**, configurabile (`AFK_CHANNEL_NAME`).
9. **Rimandati**: reazioni emoji, dashboard web, musica, soundboard, blackjack/rapine, ruoli per ricchezza, UI a bottoni.
