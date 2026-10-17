"""Chess, 1v1: seat 0 plays white, seat 1 black. Rules come from python-chess; the computer player
is a small alpha-beta engine written here (iterative deepening, quiescence on captures, piece-square
tables, MVV-LVA ordering). Levels 4-5 use a local `stockfish` binary when there is one, falling back
to the built-in engine on any error.

The game ends by checkmate, stalemate, insufficient material, threefold repetition (claimed
automatically), the fifty-move rule, resignation or an agreed draw. Each side may offer a draw at
most once every 10 plies; the opponent must answer before play goes on.
"""

import random
import shutil
import time
from typing import Any, ClassVar

import chess
import chess.engine

from marione.games.base import Action, Game, IllegalMove, Mode

MATE = 100_000
INF = 1_000_000
DRAW_OFFER_GAP = 10  # plies between two offers by the same side

VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# Piece-square tables from white's point of view, rank 8 first (a8..h8, ..., a1..h1).
_PST_RAW: dict[int, list[int]] = {
    chess.PAWN: [
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    chess.KNIGHT: [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ],
    chess.BISHOP: [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ],
    chess.ROOK: [
        0, 0, 0, 0, 0, 0, 0, 0,
        5, 10, 10, 10, 10, 10, 10, 5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        0, 0, 0, 5, 5, 0, 0, 0,
    ],
    chess.QUEEN: [
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ],
    chess.KING: [
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        20, 20, 0, 0, 0, 0, 20, 20,
        20, 30, 10, 0, 0, 10, 30, 20,
    ],
}  # fmt: skip
_KING_END_RAW = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
]  # fmt: skip


def _tables(raw: dict[int, list[int]], king: list[int]) -> dict[bool, dict[int, list[int]]]:
    """Value + square bonus indexed by python-chess square (a1 = 0) for each colour."""
    out: dict[bool, dict[int, list[int]]] = {chess.WHITE: {}, chess.BLACK: {}}
    for pt, table in {**raw, chess.KING: king}.items():
        out[chess.WHITE][pt] = [VALUES[pt] + table[sq ^ 56] for sq in chess.SQUARES]
        out[chess.BLACK][pt] = [VALUES[pt] + table[sq] for sq in chess.SQUARES]
    return out


PST_MID = _tables(_PST_RAW, _PST_RAW[chess.KING])
PST_END = _tables(_PST_RAW, _KING_END_RAW)

# level: (max depth, seconds, chance of a random move)
LEVELS: dict[int, tuple[int, float, float]] = {
    1: (1, 0.2, 0.35),
    2: (2, 0.3, 0.1),
    3: (4, 0.6, 0.0),
    4: (6, 1.0, 0.0),
    5: (8, 1.5, 0.0),
}
STOCKFISH = {4: (8, 0.4), 5: (20, 0.8)}  # level: (Skill Level, seconds)


def evaluate(board: chess.Board) -> int:
    """Material and piece-square score in centipawns, from the side to move's point of view."""
    queens = board.queens
    minors = board.knights | board.bishops | board.rooks
    endgame = not queens or chess.popcount(minors) <= 2
    tables = PST_END if endgame else PST_MID
    score = 0
    for color, sign in ((chess.WHITE, 1), (chess.BLACK, -1)):
        side = tables[color]
        for pt in chess.PIECE_TYPES:
            table = side[pt]
            for sq in chess.scan_forward(board.pieces_mask(pt, color)):
                score += sign * table[sq]
    return score if board.turn == chess.WHITE else -score


class _Timeout(Exception):
    pass


class Searcher:
    """Iterative-deepening negamax with alpha-beta and a capture-only quiescence search."""

    def __init__(self, board: chess.Board, seconds: float, max_depth: int) -> None:
        self.board = board
        self.max_depth = max_depth
        self.seconds = seconds
        self.deadline = float("inf")
        self.nodes = 0
        self.killers: dict[int, list[chess.Move]] = {}

    def _tick(self) -> None:
        self.nodes += 1
        if self.nodes & 511 == 0 and time.monotonic() > self.deadline:
            raise _Timeout

    def _order_key(self, move: chess.Move, ply: int) -> int:
        board = self.board
        if board.is_capture(move):
            victim = board.piece_type_at(move.to_square) or chess.PAWN  # en passant
            attacker = board.piece_type_at(move.from_square) or chess.PAWN
            return 10_000 + 10 * VALUES[victim] - VALUES[attacker]
        if move.promotion:
            return 9_000 + VALUES[move.promotion]
        if move in self.killers.get(ply, ()):
            return 5_000
        return 0

    def _ordered(self, moves: list[chess.Move], ply: int) -> list[chess.Move]:
        return sorted(moves, key=lambda m: self._order_key(m, ply), reverse=True)

    def quiesce(self, alpha: int, beta: int) -> int:
        self._tick()
        stand = evaluate(self.board)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        board = self.board
        captures = sorted(
            board.generate_legal_captures(), key=lambda m: self._order_key(m, 0), reverse=True
        )
        for move in captures:
            board.push(move)
            score = -self.quiesce(-beta, -alpha)
            board.pop()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def negamax(self, depth: int, alpha: int, beta: int, ply: int) -> int:
        self._tick()
        board = self.board
        if board.halfmove_clock >= 100 or board.is_repetition(2):
            return 0
        moves = list(board.legal_moves)
        if not moves:
            return -(MATE - ply) if board.is_check() else 0
        if board.is_insufficient_material():
            return 0
        if board.is_check() and ply < 2 * self.max_depth:
            depth += 1
        if depth <= 0:
            return self.quiesce(alpha, beta)
        best = -INF
        for move in self._ordered(moves, ply):
            board.push(move)
            score = -self.negamax(depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if not board.is_capture(move):
                    killers = self.killers.setdefault(ply, [])
                    if move not in killers:
                        killers.insert(0, move)
                        del killers[2:]
                break
        return best

    def search(self, margin: int = 0) -> list[tuple[chess.Move, int]]:
        """Root moves with scores from the deepest completed iteration, best first. With a
        `margin`, every move within `margin` of the best gets an exact enough score."""
        board = self.board
        root = self._ordered(list(board.legal_moves), 0)
        scored: list[tuple[chess.Move, int]] = [(m, 0) for m in root]
        start = time.monotonic()
        for depth in range(1, self.max_depth + 1):
            # The first iteration always completes; later ones stop at the deadline.
            self.deadline = float("inf") if depth == 1 else start + self.seconds
            try:
                current: list[tuple[chess.Move, int]] = []
                best = -INF
                for move in [m for m, _ in scored]:
                    # A move scoring <= floor fails low: its score is only an upper bound.
                    floor = best - margin - (1 if margin else 0) if best > -INF else -INF
                    board.push(move)
                    try:
                        score = -self.negamax(depth - 1, -INF, -floor, 1)
                    finally:
                        board.pop()
                    current.append((move, score))
                    best = max(best, score)
            except _Timeout:
                break
            scored = sorted(current, key=lambda ms: ms[1], reverse=True)
            if scored[0][1] >= MATE - 100 or time.monotonic() - start > self.seconds / 2:
                break  # a mate is found, or the next iteration would not finish
        return scored


def seat_color(seat: int) -> chess.Color:
    return chess.WHITE if seat == 0 else chess.BLACK


class Chess(Game):
    key: ClassVar[str] = "chess"
    modes: ClassVar[tuple[Mode, ...]] = (Mode("1v1", 2),)

    def __init__(
        self, mode: Mode, rng: random.Random, options: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mode, rng, options)
        try:
            level = int(self.options.get("level", 3))
        except (TypeError, ValueError):
            level = 3
        self.level = min(5, max(1, level))
        max_plies = self.options.get("max_plies")
        self.max_plies: int | None = int(max_plies) if max_plies else None
        self.board = chess.Board()
        self.sans: list[str] = []
        self.captured: dict[str, list[str]] = {"w": [], "b": []}
        self.draw_offer: int | None = None  # the seat that offered, awaiting an answer
        self.last_offer: dict[int, int] = {}  # seat -> ply of its last offer
        self.result: str | None = None
        self.reason: str | None = None

    # --- rules -------------------------------------------------------------------------------

    def _turn_seat(self) -> int:
        return 0 if self.board.turn == chess.WHITE else 1

    @property
    def finished(self) -> bool:
        return self.result is not None

    def to_act(self) -> list[int]:
        if self.finished:
            return []
        if self.draw_offer is not None:
            return [1 - self.draw_offer]
        return [self._turn_seat()]

    def _can_offer(self, seat: int) -> bool:
        last = self.last_offer.get(seat)
        return last is None or len(self.board.move_stack) - last >= DRAW_OFFER_GAP

    def legal(self, seat: int) -> list[Action]:
        if self.finished or seat not in self.to_act():
            return []
        if self.draw_offer is not None:
            return [{"type": "accept_draw"}, {"type": "decline_draw"}]
        actions: list[Action] = [{"type": "move", "uci": m.uci()} for m in self.board.legal_moves]
        actions.append({"type": "resign"})
        if self._can_offer(seat):
            actions.append({"type": "offer_draw"})
        return actions

    def act(self, seat: int, action: Action) -> None:
        if self.finished:
            raise IllegalMove("the game is over")
        if seat not in (0, 1):
            raise IllegalMove("no such seat")
        kind = action.get("type")
        if kind == "resign":  # allowed at any moment, even on the opponent's turn
            self.draw_offer = None
            self._end("0-1" if seat == 0 else "1-0", "resign")
            self.log.add("resign", seat=seat)
            return
        if seat not in self.to_act():
            raise IllegalMove("not your turn")
        if self.draw_offer is not None:
            if kind == "accept_draw":
                self.draw_offer = None
                self.log.add("draw_accepted", seat=seat)
                self._end("1/2-1/2", "draw_agreed")
            elif kind == "decline_draw":
                self.draw_offer = None
                self.log.add("draw_declined", seat=seat)
            else:
                raise IllegalMove("answer the draw offer first")
            return
        if kind == "offer_draw":
            if not self._can_offer(seat):
                raise IllegalMove("draw already offered recently")
            self.draw_offer = seat
            self.last_offer[seat] = len(self.board.move_stack)
            self.log.add("draw_offer", seat=seat)
            return
        if kind != "move":
            raise IllegalMove("unknown action")
        try:
            move = chess.Move.from_uci(str(action.get("uci", "")))
        except ValueError as e:
            raise IllegalMove("bad move") from e
        if move not in self.board.legal_moves:
            raise IllegalMove("illegal move")
        self._push(seat, move)

    def _push(self, seat: int, move: chess.Move) -> None:
        board = self.board
        if board.is_capture(move):
            if board.is_en_passant(move):
                victim = chess.Piece(chess.PAWN, not board.turn)
            else:
                piece = board.piece_at(move.to_square)
                assert piece is not None
                victim = piece
            self.captured["w" if board.turn == chess.WHITE else "b"].append(victim.symbol())
        san = board.san(move)
        board.push(move)
        self.sans.append(san)
        self.log.add("move", seat=seat, san=san, uci=move.uci())
        self._check_end()

    def _check_end(self) -> None:
        board = self.board
        if board.is_checkmate():
            self._end("0-1" if board.turn == chess.WHITE else "1-0", "checkmate")
        elif board.is_stalemate():
            self._end("1/2-1/2", "stalemate")
        elif board.is_insufficient_material():
            self._end("1/2-1/2", "material")
        elif board.is_repetition(3):
            self._end("1/2-1/2", "repetition")
        elif board.halfmove_clock >= 100:
            self._end("1/2-1/2", "fifty")
        elif self.max_plies is not None and len(board.move_stack) >= self.max_plies:
            self._end("1/2-1/2", "limit")

    def _end(self, result: str, reason: str) -> None:
        self.result, self.reason = result, reason
        self.log.add("end", result=result, reason=reason)

    def winners(self) -> list[int]:
        if self.result == "1-0":
            return [0]
        if self.result == "0-1":
            return [1]
        return []

    def summary(self) -> dict[str, Any]:
        return {"result": self.result, "reason": self.reason, "moves": list(self.sans)}

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        if self.finished or seat not in self.to_act():
            raise IllegalMove("the bot has nothing to do")
        if self.draw_offer is not None:
            # The offerer is to move: a good score for them is a bad one for the bot.
            score = -Searcher(self.board.copy(), 0.1, 1).quiesce(-INF, INF)
            return {"type": "accept_draw" if score < -150 else "decline_draw"}
        return {"type": "move", "uci": self.bot_move().uci()}

    def bot_move(self) -> chess.Move:
        moves = list(self.board.legal_moves)
        if len(moves) == 1:
            return moves[0]
        if self.level >= 4 and shutil.which("stockfish"):
            move = self._stockfish_move()
            if move is not None and move in self.board.legal_moves:
                return move
        depth, seconds, blunder = LEVELS[self.level]
        if blunder and self.rng.random() < blunder:
            return self.rng.choice(moves)
        opening = len(self.board.move_stack) < 10 and self.level >= 2
        margin = 25 if opening else 0
        scored = Searcher(self.board.copy(), seconds, depth).search(margin)
        best = scored[0][1]
        if opening:
            pool = [m for m, s in scored if s >= best - margin]
            return self.rng.choice(pool)
        return scored[0][0]

    def _stockfish_move(self) -> chess.Move | None:
        path = shutil.which("stockfish")
        if path is None:
            return None
        skill, seconds = STOCKFISH[self.level]
        try:
            engine = chess.engine.SimpleEngine.popen_uci(path, timeout=5.0)
            try:
                engine.configure({"Skill Level": skill})
                played = engine.play(self.board, chess.engine.Limit(time=seconds))
                return played.move
            finally:
                engine.quit()
        except (chess.engine.EngineError, OSError, TimeoutError):
            return None

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        board = self.board
        by_square: dict[str, list[str]] = {}
        if not self.finished and self.draw_offer is None:
            for m in board.legal_moves:
                targets = by_square.setdefault(chess.square_name(m.from_square), [])
                to = chess.square_name(m.to_square)
                if to not in targets:
                    targets.append(to)
        return {
            "fen": board.fen(),
            "turn": "w" if board.turn == chess.WHITE else "b",
            "lastMove": board.peek().uci() if board.move_stack else None,
            "check": board.is_check(),
            "moves": list(self.sans),
            "captured": {"w": list(self.captured["w"]), "b": list(self.captured["b"])},
            "result": self.result,
            "reason": self.reason,
            "drawOffer": self.draw_offer,
            "legalBySquare": by_square,
        }
