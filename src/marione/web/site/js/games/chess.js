// Chess: a wooden board seen from your side, click or drag a piece to move it, a side panel with
// the moves, captured pieces, draw offers and resignation. Your move shows at once (optimistic)
// while the server and the bot answer.
import { h, fill } from '../util.js';
import { local } from './common.js';

const tr = local({
  en: {
    white: 'White', black: 'Black', you: 'you', toMove: 'to move', thinking: 'thinking…',
    moves: 'Moves', noMoves: 'No moves yet', offerDraw: 'Offer draw', resign: 'Resign',
    resignAsk: 'Resign this game?', resignYes: 'Yes, resign', cancel: 'Cancel',
    drawOffered: '{name} offers a draw', accept: 'Accept', decline: 'Decline',
    drawPending: 'Draw offered: waiting for {name}…', check: 'Check!',
    yourMove: 'Your move', waiting: 'Waiting for {name}', promoteTo: 'Promote to',
    king: 'king', pawn: 'pawn', queen: 'Queen', rook: 'Rook', bishop: 'Bishop', knight: 'Knight',
    winsBy: '{side} wins', draw: 'Draw',
    r_checkmate: 'by checkmate', r_stalemate: 'by stalemate', r_resign: 'by resignation',
    r_draw_agreed: 'by agreement', r_repetition: 'by threefold repetition', r_fifty: 'by the fifty-move rule',
    r_material: 'by insufficient material', r_limit: 'by move limit',
    board: 'Chess board', square: '{sq}', empty: 'empty', captured: 'Captured', drawSoon: 'You can offer a draw again later',
  },
  it: {
    white: 'Bianco', black: 'Nero', you: 'tu', toMove: 'muove', thinking: 'sta pensando…',
    moves: 'Mosse', noMoves: 'Nessuna mossa', offerDraw: 'Proponi patta', resign: 'Abbandona',
    resignAsk: 'Abbandonare la partita?', resignYes: 'Sì, abbandono', cancel: 'Annulla',
    drawOffered: '{name} propone la patta', accept: 'Accetta', decline: 'Rifiuta',
    drawPending: 'Patta proposta: in attesa di {name}…', check: 'Scacco!',
    yourMove: 'Tocca a te', waiting: 'In attesa di {name}', promoteTo: 'Promuovi a',
    king: 're', pawn: 'pedone', queen: 'Donna', rook: 'Torre', bishop: 'Alfiere', knight: 'Cavallo',
    winsBy: 'Vince il {side}', draw: 'Patta',
    r_checkmate: 'per scacco matto', r_stalemate: 'per stallo', r_resign: 'per abbandono',
    r_draw_agreed: 'di comune accordo', r_repetition: 'per triplice ripetizione', r_fifty: 'per la regola delle 50 mosse',
    r_material: 'per materiale insufficiente', r_limit: 'per limite di mosse',
    board: 'Scacchiera', square: '{sq}', empty: 'vuota', captured: 'Catturati', drawSoon: 'Potrai riproporre la patta più avanti',
  },
  fr: {
    white: 'Blancs', black: 'Noirs', you: 'vous', toMove: 'au trait', thinking: 'réfléchit…',
    moves: 'Coups', noMoves: 'Aucun coup', offerDraw: 'Proposer nulle', resign: 'Abandonner',
    resignAsk: 'Abandonner la partie ?', resignYes: 'Oui, abandonner', cancel: 'Annuler',
    drawOffered: '{name} propose la nulle', accept: 'Accepter', decline: 'Refuser',
    drawPending: 'Nulle proposée : en attente de {name}…', check: 'Échec !',
    yourMove: 'À vous de jouer', waiting: 'En attente de {name}', promoteTo: 'Promouvoir en',
    king: 'roi', pawn: 'pion', queen: 'Dame', rook: 'Tour', bishop: 'Fou', knight: 'Cavalier',
    winsBy: 'Les {side} gagnent', draw: 'Partie nulle',
    r_checkmate: 'par échec et mat', r_stalemate: 'par pat', r_resign: 'par abandon',
    r_draw_agreed: 'par accord mutuel', r_repetition: 'par triple répétition', r_fifty: 'par la règle des 50 coups',
    r_material: 'par matériel insuffisant', r_limit: 'par limite de coups',
    board: 'Échiquier', square: '{sq}', empty: 'vide', captured: 'Pris', drawSoon: 'Vous pourrez reproposer la nulle plus tard',
  },
});

// Solid glyphs for both sides (coloured in CSS); U+FE0E keeps the pawn from turning into an emoji.
const GLYPH = { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟︎' };
const VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
const PIECE_NAME = { k: 'king', q: 'queen', r: 'rook', b: 'bishop', n: 'knight', p: 'pawn' };
const FILES = 'abcdefgh';

let drag = null; // the piece being dragged (module-level: survives re-renders)

/** FEN placement -> {square: 'P'|'k'|...}. */
function parseFen(fen) {
  const out = {};
  const rows = (fen || '').split(' ')[0].split('/');
  rows.forEach((row, i) => {
    const rank = 8 - i;
    let f = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) f += Number(ch);
      else { out[FILES[f] + rank] = ch; f += 1; }
    }
  });
  return out;
}

const isWhite = (p) => p && p === p.toUpperCase();

/** Plays a move on a parsed board (castling, en passant, promotion), for the optimistic view. */
function applyMove(board, uci) {
  const b = { ...board };
  const from = uci.slice(0, 2), to = uci.slice(2, 4), promo = uci[4];
  const p = b[from];
  if (!p) return b;
  const kind = p.toLowerCase();
  const df = FILES.indexOf(to[0]) - FILES.indexOf(from[0]);
  if (kind === 'p' && df !== 0 && !b[to]) delete b[to[0] + from[1]]; // en passant
  if (kind === 'k' && Math.abs(df) === 2) { // castling: the rook jumps over
    const rank = from[1];
    const [rf, rt] = df > 0 ? ['h', 'f'] : ['a', 'd'];
    b[rt + rank] = b[rf + rank];
    delete b[rf + rank];
  }
  delete b[from];
  b[to] = promo ? (isWhite(p) ? promo.toUpperCase() : promo) : p;
  return b;
}

function pieceEl(p, extra) {
  const white = isWhite(p);
  return h('span', { class: 'chs-pc ' + (white ? 'w' : 'b') + (extra ? ' ' + extra : ''), 'aria-hidden': 'true' }, GLYPH[p.toLowerCase()]);
}

export function render(el, tb, ctx) {
  const st = tb.state;
  const L = ctx.local;
  const me = tb.you;
  const myColor = me === 1 ? 'b' : 'w';
  const flip = me === 1;

  // Drop UI state that belongs to an older position.
  if (L.pending && L.pending.version !== tb.version) L.pending = null;
  if (L.fen !== st.fen) { L.fen = st.fen; L.sel = null; L.promo = null; }
  if (tb.status !== 'playing') { L.sel = null; L.promo = null; L.confirmResign = false; }

  const legalUci = new Set((tb.legal || []).filter((a) => a.type === 'move').map((a) => a.uci));
  const pending = L.pending;
  const myTurn = !pending && tb.status === 'playing' && legalUci.size > 0 && st.turn === myColor;

  let board = parseFen(st.fen);
  let lastMove = st.lastMove;
  let turn = st.turn;
  if (pending) { board = applyMove(board, pending.uci); lastMove = pending.uci; turn = st.turn === 'w' ? 'b' : 'w'; }

  const targets = (from) => (myTurn ? (st.legalBySquare || {})[from] || [] : []);
  const mine = (sq) => board[sq] && (isWhite(board[sq]) ? 'w' : 'b') === myColor;

  // Animation of the last move: only once per move.
  const moveKey = lastMove ? (st.moves.length + (pending ? 1 : 0)) + ':' + lastMove : '';
  const animate = moveKey && L.animKey !== moveKey && !(pending && pending.dragged);
  L.animKey = moveKey;

  const rerender = () => render(el, ctx.table || tb, ctx);

  async function play(from, to, promo, dragged) {
    const uci = from + to + (promo || '');
    if (!legalUci.has(uci)) return;
    L.sel = null; L.promo = null;
    L.pending = { uci, version: tb.version, dragged };
    if (dragged) L.animKey = (st.moves.length + 1) + ':' + uci;
    rerender();
    await ctx.act({ type: 'move', uci });
    if (L.pending && L.pending.uci === uci) { L.pending = null; rerender(); }
  }

  function tryMove(from, to, dragged) {
    if (!targets(from).includes(to)) return false;
    if (legalUci.has(from + to)) { play(from, to, '', dragged); return true; }
    if (legalUci.has(from + to + 'q')) { L.promo = { from, to }; L.sel = from; rerender(); return true; }
    return false;
  }

  function clickSquare(sq) {
    if (Date.now() < (L.noClickUntil || 0)) return;
    if (!myTurn) return;
    if (L.promo) { L.promo = null; rerender(); return; }
    if (L.sel && L.sel !== sq && tryMove(L.sel, sq, false)) return;
    if (mine(sq) && targets(sq).length && L.sel !== sq) L.sel = sq;
    else L.sel = null;
    rerender();
  }

  // --- drag and drop with pointer events -----------------------------------------------------
  function pointerDown(e, sq) {
    if (!myTurn || !mine(sq) || !targets(sq).length || e.button > 0) return;
    const sqEl = e.currentTarget;
    const rect = sqEl.getBoundingClientRect();
    drag = { from: sq, x0: e.clientX, y0: e.clientY, size: rect.width, ghost: null, srcEl: sqEl, started: false, tryMove, rerender, L };
    window.addEventListener('pointermove', pointerMove);
    window.addEventListener('pointerup', pointerUp);
    window.addEventListener('pointercancel', pointerCancel);
  }

  // --- the board -------------------------------------------------------------------------------
  const ranks = flip ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
  const files = flip ? [...FILES].reverse() : [...FILES];
  const lmFrom = lastMove ? lastMove.slice(0, 2) : null, lmTo = lastMove ? lastMove.slice(2, 4) : null;
  const inCheck = !pending && st.check;
  const checkSq = inCheck ? Object.keys(board).find((s) => board[s] === (st.turn === 'w' ? 'K' : 'k')) : null;
  const selTargets = L.sel ? targets(L.sel) : [];

  const squares = [];
  ranks.forEach((rank, ri) => files.forEach((file, fi) => {
    const sq = file + rank;
    const p = board[sq];
    const light = (FILES.indexOf(file) + rank) % 2 === 1;
    const isTarget = selTargets.includes(sq);
    const cls = ['chs-sq', light ? 'light' : 'dark'];
    if (sq === lmFrom || sq === lmTo) cls.push('last');
    if (sq === L.sel) cls.push('sel');
    if (isTarget) cls.push(p ? 'cap' : 'dot');
    if (sq === checkSq) cls.push('check');
    const movable = myTurn && p && mine(sq) && targets(sq).length;
    if (movable) cls.push('movable');
    let pc = null;
    if (p) {
      let extra = '';
      const style = {};
      if (animate && sq === lmTo && lmFrom) {
        const dx = (FILES.indexOf(lmFrom[0]) - FILES.indexOf(lmTo[0])) * (flip ? -1 : 1);
        const dy = (Number(lmFrom[1]) - Number(lmTo[1])) * (flip ? 1 : -1);
        extra = 'slide';
        style['--dx'] = String(dx); style['--dy'] = String(dy);
      }
      pc = pieceEl(p, extra);
      if (extra) Object.entries(style).forEach(([k, v]) => pc.style.setProperty(k, v));
    }
    const label = sq + ' ' + (p ? ((isWhite(p) ? tr('white') : tr('black')) + ' ' + tr(PIECE_NAME[p.toLowerCase()]).toLowerCase()) : tr('empty'));
    squares.push(h('button', {
      type: 'button', class: cls.join(' '), 'data-sq': sq, 'aria-label': label,
      'aria-pressed': sq === L.sel ? 'true' : null,
      tabindex: movable || isTarget ? '0' : '-1',
      onclick: () => clickSquare(sq),
      onpointerdown: (e) => pointerDown(e, sq),
    },
    pc,
    fi === 0 ? h('span', { class: 'chs-coord rank', 'aria-hidden': 'true' }, String(rank)) : null,
    ri === 7 ? h('span', { class: 'chs-coord file', 'aria-hidden': 'true' }, file) : null));
  }));

  const promoPicker = L.promo ? h('div', { class: 'chs-promo', role: 'dialog', 'aria-label': tr('promoteTo') },
    h('p', null, tr('promoteTo')),
    h('div', { class: 'chs-promo-row' }, ['q', 'r', 'b', 'n'].map((k) => {
      const p = myColor === 'w' ? k.toUpperCase() : k;
      return h('button', { type: 'button', class: 'chs-promo-btn', 'aria-label': tr(PIECE_NAME[k]), title: tr(PIECE_NAME[k]),
        onclick: () => play(L.promo.from, L.promo.to, k, false) }, pieceEl(p));
    })),
    h('button', { type: 'button', class: 'btn ghost sm', onclick: () => { L.promo = null; L.sel = null; rerender(); } }, tr('cancel'))) : null;

  const boardEl = h('div', { class: 'chs-frame' + (myTurn ? ' myturn' : '') },
    h('div', { class: 'chs-board', role: 'group', 'aria-label': tr('board') }, squares),
    promoPicker);

  // --- player strips (opponent above, you below) ----------------------------------------------
  const material = (list) => list.reduce((n, p) => n + VALUE[p.toLowerCase()], 0);
  const capW = st.captured.w || [], capB = st.captured.b || [];
  const diff = material(capW) - material(capB); // >0: white is ahead
  const order = (list) => list.slice().sort((a, b) => VALUE[b.toLowerCase()] - VALUE[a.toLowerCase()]);
  const strip = (seat) => {
    const color = seat === 0 ? 'w' : 'b';
    const taken = order(color === 'w' ? capW : capB);
    const adv = color === 'w' ? diff : -diff;
    const active = tb.status === 'playing' && turn === color;
    return h('div', { class: 'chs-player' + (active ? ' active' : '') + (seat === me ? ' me' : '') },
      h('span', { class: 'chs-badge ' + color, 'aria-hidden': 'true' }, GLYPH.k),
      h('div', { class: 'chs-pname' },
        h('strong', null, ctx.name(seat), seat === me ? h('small', null, ' · ' + tr('you')) : null),
        h('small', null, color === 'w' ? tr('white') : tr('black'),
          active ? h('span', { class: 'chs-tomove' }, ' · ' + (seat === me ? tr('toMove') : (tb.seats[seat] && tb.seats[seat].bot ? tr('thinking') : tr('toMove')))) : null)),
      h('div', { class: 'chs-caps', 'aria-label': tr('captured') + ': ' + taken.length },
        taken.map((p) => pieceEl(p, 'mini')),
        adv > 0 ? h('span', { class: 'chs-adv' }, '+' + adv) : null));
  };
  const topSeat = me === 1 ? 0 : 1, bottomSeat = me === 1 ? 1 : 0;
  const boardCol = h('div', { class: 'chs-col' }, strip(topSeat), boardEl, strip(bottomSeat));

  // --- side panel --------------------------------------------------------------------------------
  const status = statusBox(tb, st, ctx, { myTurn, pending, me, turn });
  const moves = st.moves.slice();
  const pairs = [];
  for (let i = 0; i < moves.length; i += 2) pairs.push([i / 2 + 1, moves[i], moves[i + 1]]);
  const lastIdx = moves.length - 1;
  const moveList = h('div', { class: 'chs-moves', tabindex: '0', 'aria-label': tr('moves') },
    pairs.length ? h('ol', null, pairs.map(([n, w, b], i) => h('li', null,
      h('span', { class: 'n' }, n + '.'),
      h('span', { class: 'm' + (i * 2 === lastIdx ? ' cur' : '') }, w),
      h('span', { class: 'm' + (i * 2 + 1 === lastIdx ? ' cur' : '') }, b || '')))) : h('p', { class: 'muted small' }, tr('noMoves')));

  const actions = tb.status === 'playing' && me != null ? actionsBox(tb, st, ctx, L, rerender) : null;

  const panel = h('aside', { class: 'chs-panel' },
    status,
    h('div', { class: 'chs-movebox' }, h('h3', null, tr('moves')), moveList),
    actions);

  fill(el, h('div', { class: 'chs-table' }, boardCol, panel));
  moveList.scrollTop = moveList.scrollHeight;
}

function statusBox(tb, st, ctx, { myTurn, pending, me, turn }) {
  if (st.result) {
    const winner = st.result === '1-0' ? 'w' : st.result === '0-1' ? 'b' : null;
    const head = winner ? tr('winsBy', { side: winner === 'w' ? tr('white') : tr('black') }) : tr('draw');
    const mineWin = winner && me != null && (winner === 'w') === (me === 0);
    return h('div', { class: 'chs-status over ' + (winner ? (me == null ? 'win' : mineWin ? 'win' : 'lose') : 'draw'), role: 'status' },
      h('strong', null, st.result.replace('1/2', '½').replace('1/2', '½')),
      h('span', null, head + ' ' + (st.reason ? tr('r_' + st.reason) : '')));
  }
  if (tb.status !== 'playing') return null;
  const other = turn === 'w' ? 0 : 1;
  const check = st.check && !pending;
  if (st.drawOffer != null && me != null && st.drawOffer !== me) {
    return h('div', { class: 'chs-status mine', role: 'status', 'aria-live': 'polite' },
      h('strong', null, '🤝 ' + tr('drawOffered', { name: ctx.name(st.drawOffer) })));
  }
  return h('div', { class: 'chs-status' + (myTurn ? ' mine' : ''), role: 'status', 'aria-live': 'polite' },
    h('strong', null, myTurn ? tr('yourMove') : tr('waiting', { name: ctx.name(st.drawOffer != null ? 1 - st.drawOffer : other) })),
    check ? h('span', { class: 'chs-check' }, tr('check')) : null,
    tb.turnLeft != null ? h('span', { class: 'turn-left', 'data-turnleft': '' }, tb.turnLeft + 's') : null);
}

function actionsBox(tb, st, ctx, L, rerender) {
  const me = tb.you;
  const has = (type) => (tb.legal || []).some((a) => a.type === type);
  if (st.drawOffer != null && st.drawOffer !== me && has('accept_draw')) {
    return h('div', { class: 'chs-offer', role: 'alert' },
      h('p', null, '🤝 ' + tr('drawOffered', { name: ctx.name(st.drawOffer) })),
      h('div', { class: 'chs-btns' },
        h('button', { type: 'button', class: 'btn primary sm', onclick: (e) => ctx.act({ type: 'accept_draw' }, e.currentTarget) }, tr('accept')),
        h('button', { type: 'button', class: 'btn sm', onclick: (e) => ctx.act({ type: 'decline_draw' }, e.currentTarget) }, tr('decline'))));
  }
  if (L.confirmResign) {
    return h('div', { class: 'chs-offer danger', role: 'alertdialog', 'aria-label': tr('resignAsk') },
      h('p', null, '🏳️ ' + tr('resignAsk')),
      h('div', { class: 'chs-btns' },
        h('button', { type: 'button', class: 'btn danger sm', onclick: async (e) => { await ctx.act({ type: 'resign' }, e.currentTarget); L.confirmResign = false; rerender(); } }, tr('resignYes')),
        h('button', { type: 'button', class: 'btn sm', onclick: () => { L.confirmResign = false; rerender(); } }, tr('cancel'))));
  }
  const pendingOffer = st.drawOffer === me;
  const canOffer = has('offer_draw') && !L.pending;
  const myTurnNow = has('move');
  return h('div', { class: 'chs-actions' },
    pendingOffer ? h('p', { class: 'chs-note' }, tr('drawPending', { name: ctx.name(1 - me) })) : null,
    h('div', { class: 'chs-btns' },
      h('button', { type: 'button', class: 'btn sm', disabled: !canOffer, title: myTurnNow && !canOffer ? tr('drawSoon') : null,
        onclick: (e) => ctx.act({ type: 'offer_draw' }, e.currentTarget) }, '🤝 ' + tr('offerDraw')),
      h('button', { type: 'button', class: 'btn sm danger', disabled: !has('resign') || !!L.pending,
        onclick: () => { L.confirmResign = true; rerender(); } }, '🏳️ ' + tr('resign'))));
}

// --- drag handlers (module level so they keep working across re-renders) ----------------------
function pointerMove(e) {
  if (!drag) return;
  const dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
  if (!drag.started) {
    if (Math.hypot(dx, dy) < 6) return;
    drag.started = true;
    const src = drag.srcEl.querySelector('.chs-pc');
    const ghost = src ? src.cloneNode(true) : document.createElement('span');
    ghost.classList.add('chs-ghost');
    ghost.style.width = drag.size + 'px';
    ghost.style.height = drag.size + 'px';
    ghost.style.fontSize = (drag.size * 0.82) + 'px';
    document.body.append(ghost);
    drag.ghost = ghost;
    if (src) src.classList.add('lifted');
    drag.L.sel = drag.from;
    drag.srcEl.closest('.chs-board')?.querySelectorAll('.chs-sq').forEach((s) => s.classList.add('dragging'));
  }
  e.preventDefault();
  drag.ghost.style.transform = `translate(${e.clientX - drag.size / 2}px, ${e.clientY - drag.size / 2}px)`;
  const over = squareAt(e.clientX, e.clientY);
  document.querySelectorAll('.chs-sq.hover').forEach((s) => s.classList.remove('hover'));
  if (over) over.classList.add('hover');
}

function squareAt(x, y) {
  const el = document.elementFromPoint(x, y);
  return el ? el.closest('.chs-sq') : null;
}

function endDrag() {
  window.removeEventListener('pointermove', pointerMove);
  window.removeEventListener('pointerup', pointerUp);
  window.removeEventListener('pointercancel', pointerCancel);
  if (drag && drag.ghost) drag.ghost.remove();
  const d = drag;
  drag = null;
  return d;
}

function pointerUp(e) {
  const d = endDrag();
  if (!d || !d.started) return; // a plain click: the click handler does the work
  d.L.noClickUntil = Date.now() + 80;
  const over = squareAt(e.clientX, e.clientY);
  const to = over ? over.dataset.sq : null;
  if (to && to !== d.from && d.tryMove(d.from, to, true)) return;
  d.L.sel = d.from;
  d.rerender();
}

function pointerCancel() {
  const d = endDrag();
  if (d && d.started) d.rerender();
}

export function destroy() { endDrag(); }
