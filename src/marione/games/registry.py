"""Every playable game by key, in the order the games page lists them."""

from marione.games.base import Game
from marione.games.bestia import Bestia
from marione.games.blackjack import Blackjack
from marione.games.briscola import Briscola
from marione.games.chess_game import Chess
from marione.games.machiavelli import Machiavelli
from marione.games.poker5 import Poker5
from marione.games.roulette import Roulette
from marione.games.scala40 import Scala40
from marione.games.scopa import Scopa
from marione.games.settemezzo import SetteMezzo
from marione.games.slot import Slot
from marione.games.texas import Texas
from marione.games.tresette import Tresette

GAMES: dict[str, type[Game]] = {
    cls.key: cls
    for cls in (
        Slot,
        Roulette,
        Blackjack,
        Poker5,
        Texas,
        Chess,
        Briscola,
        Scopa,
        Tresette,
        SetteMezzo,
        Scala40,
        Bestia,
        Machiavelli,
    )
}
