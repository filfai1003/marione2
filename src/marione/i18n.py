"""English (default), Italian and French texts for everything the bot and the API say.

`t(key, lang, **values)` returns the text in that language, falling back to English. The page
translates its own interface; the server translates what it sends (errors, results, history).
"""

from typing import Final

LANGS: Final = ("en", "it", "fr")
DEFAULT: Final = "en"


def normalize(lang: str | None) -> str | None:
    """'it-IT' -> 'it'; None when it is not one of ours."""
    if not lang:
        return None
    short = str(lang).strip().lower().replace("_", "-").split("-")[0]
    return short if short in LANGS else None


def unit(n: int) -> str:
    return "Marioncello" if n == 1 else "Marioncelli"


M: Final[dict[str, dict[str, str]]] = {
    # --- access -------------------------------------------------------------------------------
    "login_required": {
        "en": "Sign in with Discord.",
        "it": "Accedi con Discord.",
        "fr": "Connecte-toi avec Discord.",
    },
    "not_in_guild": {
        "en": "You're not in the server.",
        "it": "Non sei nel server.",
        "fr": "Tu n'es pas sur le serveur.",
    },
    "admin_only": {
        "en": "Only administrators can do this.",
        "it": "Solo gli amministratori possono farlo.",
        "fr": "Seuls les administrateurs peuvent faire ça.",
    },
    "too_many": {
        "en": "Too many requests: wait a moment.",
        "it": "Troppe richieste: aspetta un attimo.",
        "fr": "Trop de requêtes : attends un instant.",
    },
    "feature_off": {
        "en": "This feature is switched off right now.",
        "it": "Questa funzione è spenta al momento.",
        "fr": "Cette fonction est désactivée pour le moment.",
    },
    "cross_site": {
        "en": "Request from another site.",
        "it": "Richiesta da un altro sito.",
        "fr": "Requête provenant d'un autre site.",
    },
    "bad_request": {
        "en": "Something in the request is not valid.",
        "it": "Qualcosa nella richiesta non è valido.",
        "fr": "Quelque chose dans la requête n'est pas valide.",
    },
    "member_not_found": {
        "en": "Member not found.",
        "it": "Membro non trovato.",
        "fr": "Membre introuvable.",
    },
    # --- economy ------------------------------------------------------------------------------
    "pay_invalid": {
        "en": "Pick a member and a valid amount.",
        "it": "Scegli un membro e un importo valido.",
        "fr": "Choisis un membre et un montant valide.",
    },
    "pay_bad_target": {
        "en": "You can't send them to this member.",
        "it": "Non puoi mandarli a questo membro.",
        "fr": "Tu ne peux pas les envoyer à ce membre.",
    },
    "pay_self_or_bot": {
        "en": "You can't pay yourself or a bot.",
        "it": "Non puoi pagare te stesso o un bot.",
        "fr": "Tu ne peux pas te payer toi-même ni payer un bot.",
    },
    "not_enough": {
        "en": "You don't have enough Marioncelli.",
        "it": "Non hai abbastanza Marioncelli.",
        "fr": "Tu n'as pas assez de Marioncelli.",
    },
    "economy_paused": {
        "en": "The economy is on a break.",
        "it": "L'economia è in pausa.",
        "fr": "L'économie est en pause.",
    },
    "paid": {
        "en": "You sent {amount} {unit} to {name}.",
        "it": "Hai mandato {amount} {unit} a {name}.",
        "fr": "Tu as envoyé {amount} {unit} à {name}.",
    },
    "pay_public": {
        "en": "💸 **{sender}** gave **{amount} {unit}** to **{receiver}**",
        "it": "💸 **{sender}** ha dato **{amount} {unit}** a **{receiver}**",
        "fr": "💸 **{sender}** a donné **{amount} {unit}** à **{receiver}**",
    },
    "rob_pick": {
        "en": "Pick a victim and a valid amount.",
        "it": "Scegli una vittima e un importo valido.",
        "fr": "Choisis une victime et un montant valide.",
    },
    "victim_not_found": {
        "en": "Victim not found.",
        "it": "Vittima non trovata.",
        "fr": "Victime introuvable.",
    },
    "rob_unavailable": {
        "en": "Heists aren't available right now.",
        "it": "Il furto non è disponibile adesso.",
        "fr": "Les braquages ne sont pas disponibles pour le moment.",
    },
    "rob_ok": {
        "en": "🥷 **{attacker}** robbed **{victim}** of **{amount} {unit}**!",
        "it": "🥷 **{attacker}** ha svaligiato **{victim}** di **{amount} {unit}**!",
        "fr": "🥷 **{attacker}** a dévalisé **{victim}** de **{amount} {unit}** !",
    },
    "rob_caught": {
        "en": "🚨 **{attacker}** tried it on **{victim}** and got caught: a **{fine} {unit}** "
        "fine, paid to {victim}.",
        "it": "🚨 **{attacker}** ci ha provato con **{victim}** ma l'hanno beccato: multa di "
        "**{fine} {unit}** a favore di {victim}.",
        "fr": "🚨 **{attacker}** a tenté le coup sur **{victim}** et s'est fait prendre : "
        "amende de **{fine} {unit}** versée à {victim}.",
    },
    "rob_self": {
        "en": "Rob yourself? Marione admires the creativity, but no.",
        "it": "Derubare te stesso? Marione è fiero della tua creatività, ma no.",
        "fr": "Te voler toi-même ? Marione admire la créativité, mais non.",
    },
    "rob_too_small": {
        "en": "A heist is worth at least {min} {unit}.",
        "it": "Un furto vale almeno {min} {unit}.",
        "fr": "Un braquage vaut au moins {min} {unit}.",
    },
    "rob_broke": {
        "en": "You're broke: without Marioncelli you can't risk a heist.",
        "it": "Sei al verde: senza Marioncelli non puoi rischiare un furto.",
        "fr": "Tu es fauché : sans Marioncelli, pas de braquage.",
    },
    "rob_victim_poor": {
        "en": "The victim doesn't have that many Marioncelli.",
        "it": "La vittima non ha abbastanza Marioncelli.",
        "fr": "La victime n'a pas autant de Marioncelli.",
    },
    "rob_cooldown": {
        "en": "They're still looking for you: try again in {minutes} min.",
        "it": "Ti stanno ancora cercando: riprova tra {minutes} min.",
        "fr": "On te cherche encore : réessaie dans {minutes} min.",
    },
    "balance_line": {
        "en": "💰 **{name}** has **{amount} {unit}**",
        "it": "💰 **{name}** ha **{amount} {unit}**",
        "fr": "💰 **{name}** a **{amount} {unit}**",
    },
    "rank_place": {
        "en": " · #{rank} of {total}",
        "it": " · #{rank} su {total}",
        "fr": " · #{rank} sur {total}",
    },
    "leaderboard_title": {
        "en": "🏆 **Leaderboard**",
        "it": "🏆 **Classifica**",
        "fr": "🏆 **Classement**",
    },
    "nobody_rich": {
        "en": "Nobody has a Marioncello yet.",
        "it": "Nessuno ha ancora un Marioncello.",
        "fr": "Personne n'a encore de Marioncello.",
    },
    "no_moves": {"en": "No transactions.", "it": "Nessun movimento.", "fr": "Aucun mouvement."},
    # --- sounds -------------------------------------------------------------------------------
    "sound_not_found": {
        "en": "Sound not found.",
        "it": "Suono non trovato.",
        "fr": "Son introuvable.",
    },
    "not_in_voice": {
        "en": "Join a voice channel first 🎧",
        "it": "Entra prima in un canale vocale 🎧",
        "fr": "Rejoins d'abord un salon vocal 🎧",
    },
    "busy": {
        "en": "I'm already playing in another channel.",
        "it": "Sto già suonando in un altro canale.",
        "fr": "Je joue déjà dans un autre salon.",
    },
    "play_error": {
        "en": "I can't play right now, try again.",
        "it": "Non riesco a suonare adesso, riprova.",
        "fr": "Je n'arrive pas à jouer pour l'instant, réessaie.",
    },
    "soundboard_paused": {
        "en": "The soundboard is on a break.",
        "it": "La soundboard è in pausa.",
        "fr": "La soundboard est en pause.",
    },
    "volume_invalid": {
        "en": "Invalid volume.",
        "it": "Volume non valido.",
        "fr": "Volume invalide.",
    },
    "file_missing": {
        "en": "The audio file is missing.",
        "it": "Manca il file audio.",
        "fr": "Le fichier audio manque.",
    },
    "too_large": {
        "en": "The file is too big (max 8 MB).",
        "it": "Il file è troppo grande (max 8 MB).",
        "fr": "Le fichier est trop lourd (8 Mo max).",
    },
    "sound_exists": {
        "en": "A sound with this name already exists.",
        "it": "Esiste già un suono con questo nome.",
        "fr": "Un son porte déjà ce nom.",
    },
    "sound_limit": {
        "en": "The limit of sounds has been reached.",
        "it": "È stato raggiunto il limite di suoni.",
        "fr": "La limite de sons est atteinte.",
    },
    "invalid_audio": {
        "en": "Invalid audio: use short mp3, wav or ogg files.",
        "it": "Audio non valido: usa mp3, wav o ogg brevi.",
        "fr": "Audio invalide : utilise des mp3, wav ou ogg courts.",
    },
    "own_sounds_only": {
        "en": "You can only change your own sounds.",
        "it": "Puoi modificare solo i tuoi suoni.",
        "fr": "Tu ne peux modifier que tes propres sons.",
    },
    "board_added": {
        "en": "🔊 **{name}** is in the soundboard.",
        "it": "🔊 **{name}** è nella soundboard.",
        "fr": "🔊 **{name}** est dans la soundboard.",
    },
    "deleted": {"en": "🗑️ Deleted.", "it": "🗑️ Eliminato.", "fr": "🗑️ Supprimé."},
    "entrance_saved": {
        "en": "🔊 Saved **{name}** for **{member}**.",
        "it": "🔊 Salvato **{name}** per **{member}**.",
        "fr": "🔊 **{name}** enregistré pour **{member}**.",
    },
    "entrance_none": {
        "en": "{member} has no entrance sounds.",
        "it": "{member} non ha suoni d'entrata.",
        "fr": "{member} n'a aucun son d'entrée.",
    },
    "forgot": {
        "en": "🧽 Done: I forgot {count} things about you.",
        "it": "🧽 Fatto: ho dimenticato {count} cose su di te.",
        "fr": "🧽 C'est fait : j'ai oublié {count} choses sur toi.",
    },
    # --- music --------------------------------------------------------------------------------
    "music_playing": {
        "en": "🎵 Now playing: **{title}**",
        "it": "🎵 Ora suona: **{title}**",
        "fr": "🎵 Lecture en cours : **{title}**",
    },
    "music_queued": {
        "en": "➕ Queued (#{position}): **{title}**",
        "it": "➕ In coda (#{position}): **{title}**",
        "fr": "➕ Ajouté à la file (#{position}) : **{title}**",
    },
    "music_busy": {
        "en": "I'm already playing music for people in another channel.",
        "it": "Sto già facendo musica per qualcuno in un altro canale.",
        "fr": "Je joue déjà de la musique pour d'autres dans un autre salon.",
    },
    "music_queue_full": {
        "en": "The queue is full (50 songs).",
        "it": "La coda è piena (50 canzoni).",
        "fr": "La file est pleine (50 morceaux).",
    },
    "music_not_found": {
        "en": "I couldn't find anything to play.",
        "it": "Non ho trovato niente da suonare.",
        "fr": "Je n'ai rien trouvé à jouer.",
    },
    "music_error": {
        "en": "I can't play this right now (the site refused). Try another song.",
        "it": "Non riesco a suonarla adesso (il sito ha rifiutato). Prova un'altra canzone.",
        "fr": "Impossible de la jouer pour l'instant (le site a refusé). Essaie un autre morceau.",
    },
    "music_skipped": {"en": "⏭️ Skipped.", "it": "⏭️ Saltata.", "fr": "⏭️ Passé."},
    "music_stopped": {
        "en": "⏹️ Music stopped and queue cleared.",
        "it": "⏹️ Musica fermata e coda svuotata.",
        "fr": "⏹️ Musique arrêtée et file vidée.",
    },
    "music_paused": {"en": "⏸️ Paused.", "it": "⏸️ In pausa.", "fr": "⏸️ En pause."},
    "music_resumed": {"en": "▶️ Resumed.", "it": "▶️ Riparte.", "fr": "▶️ Reprise."},
    "music_nothing": {
        "en": "Nothing is playing.",
        "it": "Non sta suonando niente.",
        "fr": "Rien n'est en cours de lecture.",
    },
    "music_queue_title": {"en": "🎶 **Queue**", "it": "🎶 **Coda**", "fr": "🎶 **File d'attente**"},
    "music_next_empty": {
        "en": "Nothing after this one.",
        "it": "Dopo questa, niente.",
        "fr": "Rien après celui-ci.",
    },
    # --- admin --------------------------------------------------------------------------------
    "admin_gift": {
        "en": "🎁 +{amount} to **{name}**",
        "it": "🎁 +{amount} a **{name}**",
        "fr": "🎁 +{amount} pour **{name}**",
    },
    "admin_fine": {
        "en": "⚖️ -{amount} to **{name}**",
        "it": "⚖️ -{amount} a **{name}**",
        "fr": "⚖️ -{amount} pour **{name}**",
    },
    "admin_set": {
        "en": "✏️ **{name}** now has {amount}",
        "it": "✏️ **{name}** ora ha {amount}",
        "fr": "✏️ **{name}** a maintenant {amount}",
    },
    "move_not_found": {
        "en": "Transaction not found.",
        "it": "Movimento non trovato.",
        "fr": "Mouvement introuvable.",
    },
    "undone": {
        "en": "↩️ Undid {count} entries.",
        "it": "↩️ Annullati {count} movimenti.",
        "fr": "↩️ {count} mouvements annulés.",
    },
    "already_undone": {
        "en": "It was already undone.",
        "it": "Era già stato annullato.",
        "fr": "C'était déjà annulé.",
    },
    "feature_set": {
        "en": "{icon} **{name}**: {state}",
        "it": "{icon} **{name}**: {state}",
        "fr": "{icon} **{name}** : {state}",
    },
    "on": {"en": "on", "it": "attiva", "fr": "activée"},
    "off": {"en": "off", "it": "spenta", "fr": "désactivée"},
    "legacy_missing": {
        "en": "I can't find the #marione-data channel.",
        "it": "Non trovo il canale #marione-data.",
        "fr": "Je ne trouve pas le salon #marione-data.",
    },
    "legacy_done": {
        "en": "📦 Imported: {summary}.",
        "it": "📦 Importati: {summary}.",
        "fr": "📦 Importé : {summary}.",
    },
    "lang_set": {
        "en": "🌍 Language set to English.",
        "it": "🌍 Lingua impostata: italiano.",
        "fr": "🌍 Langue définie : français.",
    },
    "model_invalid": {
        "en": "That model is not available on OpenRouter.",
        "it": "Questo modello non è disponibile su OpenRouter.",
        "fr": "Ce modèle n'est pas disponible sur OpenRouter.",
    },
    # --- ledger entries -----------------------------------------------------------------------
    "r.chat_reward": {
        "en": "Chat messages",
        "it": "Messaggi in chat",
        "fr": "Messages dans le chat",
    },
    "r.voice_reward": {"en": "Time in voice", "it": "Tempo in vocale", "fr": "Temps en vocal"},
    "r.spam_fine": {"en": "Anti-spam fine", "it": "Multa antispam", "fr": "Amende anti-spam"},
    "r.afk_fine": {"en": "AFK fine", "it": "Multa AFK", "fr": "Amende AFK"},
    "r.afk_drain": {"en": "AFK bed", "it": "Letto AFK", "fr": "Lit AFK"},
    "r.admin_adjust": {
        "en": "Admin adjustment",
        "it": "Intervento di un admin",
        "fr": "Intervention d'un admin",
    },
    "r.reversal": {
        "en": "Operation undone",
        "it": "Operazione annullata",
        "fr": "Opération annulée",
    },
    "r.game_bet": {
        "en": "Bet at the games table",
        "it": "Puntata ai giochi",
        "fr": "Mise aux jeux",
    },
    "r.game_win": {"en": "Won at the games table", "it": "Vinto ai giochi", "fr": "Gagné aux jeux"},
    "r.game_refund": {
        "en": "Games: stake returned",
        "it": "Giochi: posta restituita",
        "fr": "Jeux : mise rendue",
    },
    "game.not_found": {
        "en": "That table is gone.",
        "it": "Quel tavolo non c'è più.",
        "fr": "Cette table n'existe plus.",
    },
    "game.forbidden": {
        "en": "You can't do that at this table.",
        "it": "Non puoi farlo a questo tavolo.",
        "fr": "Tu ne peux pas faire ça à cette table.",
    },
    "game.unknown_game": {"en": "Unknown game.", "it": "Gioco sconosciuto.", "fr": "Jeu inconnu."},
    "game.unknown_mode": {
        "en": "Unknown mode for this game.",
        "it": "Modalità sconosciuta per questo gioco.",
        "fr": "Mode inconnu pour ce jeu.",
    },
    "game.bad_stake": {"en": "Invalid stake.", "it": "Posta non valida.", "fr": "Mise invalide."},
    "game.illegal": {
        "en": "That move isn't allowed.",
        "it": "Mossa non consentita.",
        "fr": "Coup non autorisé.",
    },
    "game.not_your_turn": {
        "en": "It's not your turn.",
        "it": "Non è il tuo turno.",
        "fr": "Ce n'est pas ton tour.",
    },
    "game.not_playing": {
        "en": "The match isn't running.",
        "it": "La partita non è in corso.",
        "fr": "La partie n'est pas en cours.",
    },
    "game.already_started": {
        "en": "The match has already started.",
        "it": "La partita è già iniziata.",
        "fr": "La partie a déjà commencé.",
    },
    "game.table_full": {
        "en": "The table is full.",
        "it": "Il tavolo è pieno.",
        "fr": "La table est pleine.",
    },
    "game.seat_taken": {
        "en": "That seat is taken.",
        "it": "Quel posto è occupato.",
        "fr": "Cette place est prise.",
    },
    "game.not_a_bot": {
        "en": "That seat isn't a bot.",
        "it": "Quel posto non è un bot.",
        "fr": "Cette place n'est pas un bot.",
    },
    "game.insufficient_funds": {
        "en": "Not enough Marioncelli.",
        "it": "Non hai abbastanza Marioncelli.",
        "fr": "Pas assez de Marioncelli.",
    },
    "game.too_many_tables": {
        "en": "Too many tables open: try later.",
        "it": "Troppi tavoli aperti: riprova più tardi.",
        "fr": "Trop de tables ouvertes : réessaie plus tard.",
    },
    "game.too_many_yours": {
        "en": "You're already at 3 tables.",
        "it": "Sei già seduto a 3 tavoli.",
        "fr": "Tu es déjà à 3 tables.",
    },
    "r.legacy_import": {
        "en": "Balance from the old Marione",
        "it": "Saldo dal vecchio Marione",
        "fr": "Solde de l'ancien Marione",
    },
    "r.transfer_out": {"en": "Sent to {who}", "it": "Mandati a {who}", "fr": "Envoyés à {who}"},
    "r.transfer_in": {
        "en": "Received from {who}",
        "it": "Ricevuti da {who}",
        "fr": "Reçus de {who}",
    },
    "r.rob_out": {"en": "Robbed by {who}", "it": "Svaligiato da {who}", "fr": "Dévalisé par {who}"},
    "r.rob_in": {"en": "Robbed {who}", "it": "Svaligiato {who}", "fr": "Dévalisé {who}"},
    "r.rob_fine_out": {
        "en": "Fine for the heist on {who}",
        "it": "Multa per il furto a {who}",
        "fr": "Amende pour le braquage de {who}",
    },
    "r.rob_fine_in": {
        "en": "Fine paid by {who}",
        "it": "Multa pagata da {who}",
        "fr": "Amende payée par {who}",
    },
    "r.agent_fine_out": {"en": "Fined by {who}", "it": "Multa di {who}", "fr": "Amende de {who}"},
    "r.agent_fine_in": {"en": "Fine collected", "it": "Multa incassata", "fr": "Amende encaissée"},
    "r.agent_gift_out": {"en": "Gift to {who}", "it": "Regalo a {who}", "fr": "Cadeau à {who}"},
    "r.agent_gift_in": {"en": "Gift from {who}", "it": "Regalo di {who}", "fr": "Cadeau de {who}"},
    "someone": {"en": "someone", "it": "qualcuno", "fr": "quelqu'un"},
}


def t(key: str, lang: str | None = None, **values: object) -> str:
    texts = M.get(key)
    if texts is None:
        return key
    text = texts.get(lang or DEFAULT) or texts[DEFAULT]
    return text.format(**values) if values else text
