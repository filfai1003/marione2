"""Slash command names and descriptions: English by default, shown in Italian or French to members
whose Discord app is in that language (Discord's own command localisation)."""

import discord
from discord import app_commands

# English text -> {"it": ..., "fr": ...}. Names: lowercase, no spaces, no accents.
COMMAND_TEXTS: dict[str, dict[str, str]] = {
    # groups
    "Marioncelli, sounds and more": {
        "it": "Marioncelli, suoni e altro",
        "fr": "Marioncelli, sons et plus",
    },
    "Tools for administrators": {
        "it": "Strumenti per gli amministratori",
        "fr": "Outils pour les administrateurs",
    },
    # /marione
    "balance": {"it": "saldo", "fr": "solde"},
    "How many Marioncelli you (or another member) have": {
        "it": "Quanti Marioncelli hai (o ha un altro membro)",
        "fr": "Combien de Marioncelli tu as (ou un autre membre)",
    },
    "pay": {"it": "paga", "fr": "payer"},
    "Give Marioncelli to another member": {
        "it": "Dai dei Marioncelli a un altro membro",
        "fr": "Donne des Marioncelli à un autre membre",
    },
    "rob": {"it": "deruba", "fr": "braquer"},
    "Try a heist: if you get caught you pay a fine": {
        "it": "Tenta un furto: se ti beccano paghi una multa",
        "fr": "Tente un braquage : si tu te fais prendre, tu paies une amende",
    },
    "leaderboard": {"it": "classifica", "fr": "classement"},
    "The richest members": {"it": "I più ricchi del server", "fr": "Les membres les plus riches"},
    "history": {"it": "storico", "fr": "historique"},
    "Your latest transactions": {"it": "I tuoi ultimi movimenti", "fr": "Tes derniers mouvements"},
    "Play a soundboard sound in your voice channel": {
        "it": "Suona un suono della soundboard in vocale",
        "fr": "Joue un son de la soundboard dans ton salon vocal",
    },
    "soundboard-add": {"it": "soundboard-aggiungi", "fr": "soundboard-ajouter"},
    "Add a sound to the soundboard": {
        "it": "Aggiungi un suono alla soundboard",
        "fr": "Ajoute un son à la soundboard",
    },
    "language": {"it": "lingua", "fr": "langue"},
    "The language Marione uses with you": {
        "it": "La lingua che Marione usa con te",
        "fr": "La langue que Marione utilise avec toi",
    },
    "forget": {"it": "dimentica", "fr": "oublier"},
    "Erase everything Marione remembers about you": {
        "it": "Cancella tutto quello che Marione ricorda di te",
        "fr": "Efface tout ce dont Marione se souvient sur toi",
    },
    "play": {"it": "suona", "fr": "jouer"},
    "Play a song from a link or a title": {
        "it": "Suona una canzone da un link o da un titolo",
        "fr": "Joue un morceau depuis un lien ou un titre",
    },
    "skip": {"it": "salta", "fr": "passer"},
    "Skip to the next song": {
        "it": "Passa alla prossima canzone",
        "fr": "Passe au morceau suivant",
    },
    "stop": {"it": "ferma", "fr": "arreter"},
    "Stop the music and clear the queue": {
        "it": "Ferma la musica e svuota la coda",
        "fr": "Arrête la musique et vide la file",
    },
    "pause": {"it": "pausa", "fr": "pause"},
    "Pause or resume the music": {
        "it": "Metti in pausa o riprendi la musica",
        "fr": "Met en pause ou reprend la musique",
    },
    "queue": {"it": "coda", "fr": "file"},
    "What is playing and what comes next": {
        "it": "Cosa sta suonando e cosa viene dopo",
        "fr": "Ce qui joue et ce qui suit",
    },
    "query": {"it": "cerca", "fr": "recherche"},
    # /marione-admin
    "give": {"it": "regala", "fr": "donner"},
    "Give Marioncelli to a member": {
        "it": "Dai Marioncelli a un membro",
        "fr": "Donne des Marioncelli à un membre",
    },
    "fine": {"it": "multa", "fr": "amende"},
    "Take Marioncelli from a member": {
        "it": "Togli Marioncelli a un membro",
        "fr": "Retire des Marioncelli à un membre",
    },
    "set": {"it": "imposta", "fr": "definir"},
    "Set a member's balance": {
        "it": "Imposta il saldo di un membro",
        "fr": "Définit le solde d'un membre",
    },
    "undo": {"it": "annulla", "fr": "annuler"},
    "Undo an operation by its entry number (see /marione history)": {
        "it": "Annulla un'operazione dal numero del movimento (vedi /marione storico)",
        "fr": "Annule une opération par son numéro de mouvement (voir /marione historique)",
    },
    "feature": {"it": "funzione", "fr": "fonction"},
    "Switch a feature on or off": {
        "it": "Attiva o disattiva una funzione",
        "fr": "Active ou désactive une fonction",
    },
    "status": {"it": "stato", "fr": "statut"},
    "Features, AI costs, balance check": {
        "it": "Funzioni attive, costi dell'IA, controllo dei saldi",
        "fr": "Fonctions, coûts de l'IA, contrôle des soldes",
    },
    "import-old": {"it": "importa-vecchio", "fr": "importer-ancien"},
    "Import balances, soundboard and entrance sounds from the old Marione": {
        "it": "Importa saldi, soundboard e suoni d'entrata dal vecchio Marione",
        "fr": "Importe soldes, soundboard et sons d'entrée de l'ancien Marione",
    },
    "entrance-add": {"it": "entrata-aggiungi", "fr": "entree-ajouter"},
    "Add an entrance sound for a member": {
        "it": "Aggiungi un suono d'entrata a un membro",
        "fr": "Ajoute un son d'entrée à un membre",
    },
    "entrance-list": {"it": "entrata-lista", "fr": "entree-liste"},
    "A member's entrance sounds": {
        "it": "I suoni d'entrata di un membro",
        "fr": "Les sons d'entrée d'un membre",
    },
    "entrance-remove": {"it": "entrata-rimuovi", "fr": "entree-supprimer"},
    "Delete an entrance sound of a member": {
        "it": "Elimina un suono d'entrata di un membro",
        "fr": "Supprime un son d'entrée d'un membre",
    },
    "soundboard-remove": {"it": "soundboard-rimuovi", "fr": "soundboard-supprimer"},
    "Delete a sound from the soundboard": {
        "it": "Elimina un suono dalla soundboard",
        "fr": "Supprime un son de la soundboard",
    },
    "server-language": {"it": "lingua-server", "fr": "langue-serveur"},
    "Language of Marione's public messages in this server": {
        "it": "Lingua dei messaggi pubblici di Marione nel server",
        "fr": "Langue des messages publics de Marione sur le serveur",
    },
    # parameters
    "member": {"it": "membro", "fr": "membre"},
    "amount": {"it": "importo", "fr": "montant"},
    "name": {"it": "nome", "fr": "nom"},
    "sound": {"it": "suono", "fr": "son"},
    "entry": {"it": "movimento", "fr": "mouvement"},
    "enabled": {"it": "attiva", "fr": "active"},
    "file": {"it": "file", "fr": "fichier"},
    "emoji": {"it": "emoji", "fr": "emoji"},
}

_LOCALES = {discord.Locale.italian: "it", discord.Locale.french: "fr"}


class Translator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        lang = _LOCALES.get(locale)
        if lang is None:
            return None
        return COMMAND_TEXTS.get(string.message, {}).get(lang)
