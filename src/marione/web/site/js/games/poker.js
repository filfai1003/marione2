// Poker: Texas Hold'em and five-card draw (fixed limit). One table object is one hand.
// An oval table with the seats around it (you at the bottom), each seat's bet in front of it,
// the board and the pot in the middle, your hand below and the action bar under it.
import { h, fill, fmt } from '../util.js';
import { card, pile } from '../art.js';
import { turnBanner, local } from './common.js';

const tr = local({
  en: {
    'ph.blinds': 'Blinds', 'ph.ante': 'Antes', 'ph.preflop': 'Pre-flop', 'ph.flop': 'Flop', 'ph.turn': 'Turn', 'ph.river': 'River',
    'ph.bet1': 'First betting round', 'ph.draw': 'The draw', 'ph.bet2': 'Second betting round', 'ph.showdown': 'Showdown', 'ph.over': 'Hand over',
    'rk.high_card': 'High card', 'rk.pair': 'Pair', 'rk.two_pair': 'Two pair', 'rk.three': 'Three of a kind', 'rk.straight': 'Straight',
    'rk.flush': 'Flush', 'rk.full_house': 'Full house', 'rk.four': 'Four of a kind', 'rk.straight_flush': 'Straight flush', 'rk.royal_flush': 'Royal flush',
    fold: 'Fold', check: 'Check', call: 'Call {n}', bet: 'Bet {n}', raise: 'Raise {n}', blind: 'Post blind {n}', ante: 'Pay ante {n}', sitOut: 'Sit this hand out',
    change: 'Change {n} cards', change1: 'Change 1 card', standPat: 'Stand pat', tapDiscard: 'Tap the cards you want to change',
    pot: 'Pot', toCall: 'To call: {n}', cap: 'Bets {a}/{b}', capped: 'Betting capped', blindsInfo: 'Blinds {s}/{b}', anteInfo: 'Ante {n}',
    yourHand: 'Your hand', you: 'you', folded: 'Folded', dealer: 'Dealer', inPot: 'In pot {n}',
    'did.check': 'Check', 'did.call': 'Call {n}', 'did.bet': 'Bet {n}', 'did.raise': 'Raise {n}', 'did.blind': 'Blind {n}', 'did.ante': 'Ante {n}',
    'did.draw': 'Changed {n}', 'did.pat': 'Stood pat', 'did.fold': 'Folded',
    wins: '{name} wins {n}', withHand: 'with {hand}', allFolded: 'everyone else folded', split: 'Split pot', discard: 'Change', deck: 'Cards left',
    waitHand: 'Waiting for the cards…', handOver: 'Hand over',
  },
  it: {
    'ph.blinds': 'Bui', 'ph.ante': 'Invito', 'ph.preflop': 'Pre-flop', 'ph.flop': 'Flop', 'ph.turn': 'Turn', 'ph.river': 'River',
    'ph.bet1': 'Primo giro di puntate', 'ph.draw': 'Il cambio', 'ph.bet2': 'Secondo giro di puntate', 'ph.showdown': 'Showdown', 'ph.over': 'Mano finita',
    'rk.high_card': 'Carta alta', 'rk.pair': 'Coppia', 'rk.two_pair': 'Doppia coppia', 'rk.three': 'Tris', 'rk.straight': 'Scala',
    'rk.flush': 'Colore', 'rk.full_house': 'Full', 'rk.four': 'Poker', 'rk.straight_flush': 'Scala colore', 'rk.royal_flush': 'Scala reale',
    fold: 'Lascia', check: 'Passa', call: 'Vedo {n}', bet: 'Punta {n}', raise: 'Rilancia {n}', blind: 'Metti il buio {n}', ante: "Metti l'invito {n}", sitOut: 'Salta la mano',
    change: 'Cambia {n} carte', change1: 'Cambia 1 carta', standPat: 'Servito', tapDiscard: 'Tocca le carte che vuoi cambiare',
    pot: 'Piatto', toCall: 'Per vedere: {n}', cap: 'Puntate {a}/{b}', capped: 'Puntate al massimo', blindsInfo: 'Bui {s}/{b}', anteInfo: 'Invito {n}',
    yourHand: 'La tua mano', you: 'tu', folded: 'Ha lasciato', dealer: 'Mazziere', inPot: 'Nel piatto {n}',
    'did.check': 'Passa', 'did.call': 'Vede {n}', 'did.bet': 'Punta {n}', 'did.raise': 'Rilancia {n}', 'did.blind': 'Buio {n}', 'did.ante': 'Invito {n}',
    'did.draw': 'Ne cambia {n}', 'did.pat': 'Servito', 'did.fold': 'Ha lasciato',
    wins: '{name} vince {n}', withHand: 'con {hand}', allFolded: 'gli altri hanno lasciato', split: 'Piatto diviso', discard: 'Cambia', deck: 'Carte nel mazzo',
    waitHand: 'Si aspettano le carte…', handOver: 'Mano finita',
  },
  fr: {
    'ph.blinds': 'Blindes', 'ph.ante': 'Antes', 'ph.preflop': 'Pré-flop', 'ph.flop': 'Flop', 'ph.turn': 'Turn', 'ph.river': 'River',
    'ph.bet1': 'Premier tour d’enchères', 'ph.draw': 'L’échange', 'ph.bet2': 'Second tour d’enchères', 'ph.showdown': 'Abattage', 'ph.over': 'Main terminée',
    'rk.high_card': 'Carte haute', 'rk.pair': 'Paire', 'rk.two_pair': 'Double paire', 'rk.three': 'Brelan', 'rk.straight': 'Quinte',
    'rk.flush': 'Couleur', 'rk.full_house': 'Full', 'rk.four': 'Carré', 'rk.straight_flush': 'Quinte flush', 'rk.royal_flush': 'Quinte flush royale',
    fold: 'Se coucher', check: 'Parole', call: 'Suivre {n}', bet: 'Miser {n}', raise: 'Relancer {n}', blind: 'Payer la blinde {n}', ante: 'Payer l’ante {n}', sitOut: 'Passer cette main',
    change: 'Changer {n} cartes', change1: 'Changer 1 carte', standPat: 'Servi', tapDiscard: 'Touchez les cartes à changer',
    pot: 'Pot', toCall: 'À suivre : {n}', cap: 'Mises {a}/{b}', capped: 'Mises plafonnées', blindsInfo: 'Blindes {s}/{b}', anteInfo: 'Ante {n}',
    yourHand: 'Votre main', you: 'vous', folded: 'Couché', dealer: 'Donneur', inPot: 'Au pot {n}',
    'did.check': 'Parole', 'did.call': 'Suit {n}', 'did.bet': 'Mise {n}', 'did.raise': 'Relance {n}', 'did.blind': 'Blinde {n}', 'did.ante': 'Ante {n}',
    'did.draw': 'En change {n}', 'did.pat': 'Servi', 'did.fold': 'Couché',
    wins: '{name} gagne {n}', withHand: 'avec {hand}', allFolded: 'les autres se sont couchés', split: 'Pot partagé', discard: 'Changer', deck: 'Cartes restantes',
    waitHand: 'En attente des cartes…', handOver: 'Main terminée',
  },
});

const DECK = 'fr';
const rankName = (k) => (k ? tr('rk.' + k) : '');
const coins = (n) => fmt(n) + ' 🪙';

export function render(el, tb, ctx) {
  const st = tb.state;
  const n = tb.seats.length;
  const L = ctx.local;
  const texas = tb.game === 'texas';
  const me = tb.you;
  const over = st.phase === 'showdown' || st.phase === 'over' || tb.status === 'over';

  // what changed since the last draw (only new things animate)
  const prev = L.prev || {};
  const handKey = (st.hand || []).join(',');
  if (L.handKey !== handKey) { L.handKey = handKey; L.discard = new Set(); }
  if (!L.discard) L.discard = new Set();
  const seen = { bets: st.bets.slice(), board: (st.board || []).slice(), hand: (st.hand || []).slice(), shown: (st.showdown || []).length, mine: tb.toAct.includes(me) };
  const fresh = (kind, i, v) => !prev[kind] || prev[kind][i] !== v;
  const reveal = !prev.shown;
  L.prev = seen;

  const shown = Object.fromEntries((st.showdown || []).map((e) => [e.seat, e]));
  const winners = new Set(st.winners || []);
  const last = lastActions(tb, st);

  // ---- the seats, their bets and the dealer button --------------------------------------------
  const seats = [], bets = [];
  for (let i = 0; i < n; i++) {
    const rel = ctx.rel(i);
    const a = Math.PI / 2 + (rel * 2 * Math.PI) / n;
    const cos = Math.cos(a), sin = Math.sin(a);
    const pos = (rx, ry) => ({ '--x': (50 + rx * cos).toFixed(2), '--y': (50 + ry * sin).toFixed(2) });
    const isMe = i === me;
    const turn = tb.status === 'playing' && tb.toAct.includes(i);
    const folded = st.folded[i];
    const sd = shown[i];
    const won = st.won && st.won[String(i)];
    const cnt = st.handCounts[i] || 0;
    let cardsEl = null;
    if (sd && !isMe) {
      const best = new Set(sd.best);
      cardsEl = h('div', { class: 'pk-cards shown' + (reveal ? ' flip' : '') }, sd.cards.map((c) => card(c, { deck: DECK, size: 'sm', cls: best.has(c) ? 'pk-best' : 'pk-dim' })));
    } else if (!isMe && cnt && !folded) {
      cardsEl = h('div', { class: 'pk-cards' }, Array.from({ length: cnt }, () => card('??', { deck: DECK, size: 'xs' })));
    }
    const status = folded ? tr('folded') : last[i] || (st.contributed[i] ? tr('inPot', { n: fmt(st.contributed[i]) }) : '');
    seats.push(h('div', {
      class: 'pk-seat' + (isMe ? ' me' : '') + (turn ? ' turn' : '') + (folded ? ' folded' : '') + (winners.has(i) ? ' winner' : '')
        + (sin > 0.2 && !isMe ? ' low' : ''),
      style: pos(47, 46),
    },
    h('div', { class: 'pk-pod' },
      h('span', { class: 'pk-av', 'aria-hidden': 'true' }, avatar(tb.seats[i])),
      h('span', { class: 'pk-who' },
        h('strong', null, cleanName(ctx.name(i)), isMe ? h('small', null, ' · ' + tr('you')) : null),
        h('small', { class: 'pk-status' }, status)),
      st.button === i ? h('span', { class: 'pk-dealer', title: tr('dealer'), 'aria-label': tr('dealer') }, 'D') : null),
    cardsEl,
    sd && !isMe ? h('span', { class: 'pk-rank' + (winners.has(i) ? ' win' : '') }, rankName(sd.rank)) : null,
    won ? h('span', { class: 'pk-won', 'aria-live': 'polite' }, '+' + coins(won)) : null));
    if (st.bets[i] > 0 && !over) {
      bets.push(h('div', { class: 'pk-bet' + (fresh('bets', i, st.bets[i]) ? ' new' : ''), style: pos(31, 27) },
        chips(st.bets[i], st.unit), h('span', { class: 'pk-amt' }, fmt(st.bets[i]))));
    }
  }

  // ---- the middle: phase, board, pot -----------------------------------------------------------
  const board = st.board || [];
  const middle = h('div', { class: 'pk-mid' },
    h('span', { class: 'pk-phase' }, tr('ph.' + st.phase),
      texas ? h('small', null, ' · ' + tr('blindsInfo', { s: fmt(st.smallBlind), b: fmt(st.bigBlind) }))
        : h('small', null, ' · ' + tr('anteInfo', { n: fmt(st.ante ?? st.unit) }))),
    texas ? h('div', { class: 'pk-board' }, Array.from({ length: 5 }, (_, k) => board[k]
      ? card(board[k], { deck: DECK, size: 'md', cls: (fresh('board', k, board[k]) ? 'pk-deal ' : '') + (bestSet(st, me, shown).has(board[k]) && over ? 'pk-best' : '') })
      : h('span', { class: 'pk-slot', 'aria-hidden': 'true' })))
      : h('div', { class: 'pk-board draw' }, st.deck != null ? pile(DECK, st.deck, tr('deck')) : null),
    h('div', { class: 'pk-pot' + (over ? ' paid' : '') }, st.pot ? chips(st.pot, st.unit, 6) : null,
      h('span', null, h('small', null, tr('pot')), h('b', null, coins(st.pot)))));

  const tableEl = h('div', { class: 'pk-table n' + n + (texas ? ' texas' : ' draw5') },
    h('div', { class: 'pk-rail' }, h('div', { class: 'pk-felt' })),
    middle, bets, seats);

  // ---- your hand, the action bar ---------------------------------------------------------------
  const legal = tb.legal || [];
  const byType = Object.fromEntries(legal.map((x) => [x.type, x]));
  const drawing = !!byType.draw;
  const myShow = me != null ? shown[me] : null;
  const myBest = myShow ? new Set(myShow.best) : null;
  const hand = st.hand || [];
  const handEl = me != null ? h('div', { class: 'pk-me' + (st.folded[me] ? ' folded' : '') },
    hand.length ? h('div', { class: 'pk-hand' + (drawing ? ' picking' : '') }, hand.map((c, k) => {
      const marked = L.discard.has(c);
      const cls = (fresh('hand', k, c) ? 'pk-deal ' : '') + (marked ? 'pk-out ' : '') + (myBest ? (myBest.has(c) ? 'pk-best' : 'pk-dim') : '');
      const el2 = card(c, {
        deck: DECK, size: 'lg', cls, selected: marked,
        onClick: drawing ? () => { if (marked) L.discard.delete(c); else L.discard.add(c); render(el, tb, ctx); } : null,
      });
      return marked ? h('span', { class: 'pk-outwrap' }, el2, h('span', { class: 'pk-outtag', 'aria-hidden': 'true' }, tr('discard'))) : el2;
    })) : h('p', { class: 'pk-wait' }, st.folded[me] ? tr('folded') : tr('waitHand')),
    hand.length && (st.handName || myShow) ? h('p', { class: 'pk-handname' + (winners.has(me) ? ' win' : '') },
      h('small', null, tr('yourHand')), h('b', null, rankName(myShow ? myShow.rank : st.handName))) : null) : null;

  fill(el, h('div', { class: 'pk-wrap' },
    tableEl,
    turnBanner(tb, ctx),
    handEl,
    actionBar(tb, st, ctx, byType, L, !prev.mine),
    resultBox(tb, st, ctx, shown)));
}

/** The actions you can take now. */
function actionBar(tb, st, ctx, byType, L, pop) {
  if (tb.status !== 'playing' || !Object.keys(byType).length) return null;
  const go = (a) => (e) => ctx.act({ ...a }, e.currentTarget);
  const B = (cls, label, onclick) => h('button', { type: 'button', class: 'btn pk-act ' + cls, onclick }, label);
  if (byType.blind || byType.ante) {
    const p = byType.blind || byType.ante;
    return h('div', { class: 'pk-actions' + (pop ? ' pop' : '') },
      h('div', { class: 'pk-btns' },
        byType.fold ? B('ghost', tr('sitOut'), go(byType.fold)) : null,
        B('coin', tr(p.type, { n: fmt(p.cost) }), go(p))));
  }
  if (byType.draw) {
    const n = L.discard.size;
    return h('div', { class: 'pk-actions' + (pop ? ' pop' : '') },
      h('p', { class: 'pk-info' }, tr('tapDiscard')),
      h('div', { class: 'pk-btns' },
        B(n ? 'coin' : 'primary', n === 0 ? tr('standPat') : n === 1 ? tr('change1') : tr('change', { n }), (e) => {
          const discard = [...L.discard].filter((c) => (st.hand || []).includes(c));
          ctx.act({ type: 'draw', discard }, e.currentTarget);
        })));
  }
  const pass = byType.check || byType.call;
  const agg = byType.bet || byType.raise;
  const info = [
    st.toCall ? tr('toCall', { n: coins(st.toCall) }) : null,
    agg ? tr('cap', { a: st.raises, b: st.maxBets }) : tr('capped'),
  ].filter(Boolean).join(' · ');
  return h('div', { class: 'pk-actions' + (pop ? ' pop' : '') },
    h('p', { class: 'pk-info' }, info),
    h('div', { class: 'pk-btns' },
      byType.fold ? B('danger', tr('fold'), go(byType.fold)) : null,
      pass ? B('primary', pass.type === 'check' ? tr('check') : tr('call', { n: fmt(pass.cost) }), go(pass)) : null,
      agg ? B('coin', tr(agg.type, { n: fmt(agg.cost) }), go(agg)) : null));
}

/** Who won what, once the hand is over. */
function resultBox(tb, st, ctx, shown) {
  const ws = st.winners || [];
  if (!ws.length) return null;
  const split = ws.length > 1;
  return h('div', { class: 'pk-result' },
    split ? h('strong', { class: 'pk-split' }, tr('split')) : null,
    ws.map((s) => {
      const sd = shown[s];
      return h('p', null, '🏆 ', h('b', null, tr('wins', { name: cleanName(ctx.name(s)), n: coins(st.won[String(s)] || 0) })), ' ',
        sd ? tr('withHand', { hand: rankName(sd.rank) }) : '(' + tr('allFolded') + ')');
    }));
}

/** The latest action of each seat in the current betting round, from the log. */
function lastActions(tb, st) {
  const out = {};
  for (const e of tb.log || []) {
    if (e.kind === 'deal') { for (const k of Object.keys(out)) if (!st.folded[k]) delete out[k]; continue; }
    if (e.seat == null) continue;
    if (e.kind === 'win') continue;
    if (e.kind === 'draw') out[e.seat] = e.count ? tr('did.draw', { n: e.count }) : tr('did.pat');
    else if (['check', 'call', 'bet', 'raise', 'blind', 'ante', 'fold'].includes(e.kind)) out[e.seat] = tr('did.' + e.kind, { n: fmt(e.amount || 0) });
  }
  return out;
}

/** Board cards used by any revealed best five (to light them up at showdown). */
function bestSet(st, me, shown) {
  const s = new Set();
  for (const w of st.winners || []) if (shown[w]) shown[w].best.forEach((c) => s.add(c));
  return s;
}

/** A small stack of chips for an amount (one chip per unit, capped). */
function chips(amount, unit, max = 5) {
  const k = Math.max(1, Math.min(max, Math.ceil(amount / Math.max(1, unit))));
  return h('span', { class: 'pk-chips', 'aria-hidden': 'true' }, Array.from({ length: k }, (_, j) => h('i', { class: 'c' + (j % 3) })));
}

function avatar(seat) {
  if (!seat) return '?';
  if (seat.bot) return '🤖';
  return (seat.name || '?').trim()[0].toUpperCase();
}
const cleanName = (s) => String(s).replace(/\s*🤖\s*$/u, '');
