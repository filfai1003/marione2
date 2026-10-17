// Rummy family on French cards (two decks, so codes repeat: selections are tracked by hand index).
// scala40: stock + discard, stage melds (40 to open), lay off onto table melds, swap jokers, discard.
// machiavelli: a workspace copy of the whole table that you rearrange freely, then send it all.
import { h, fill } from '../util.js';
import { card, cardName } from '../art.js';
import { felt, opponents, turnBanner, local } from './common.js';

const tr = local({
  en: {
    sortSuit: 'Sort: suit', sortRank: 'Sort: rank', sortAria: 'Change how your hand is sorted',
    stock: 'Stock', discard: 'Discard pile', drawStock: 'Draw from the stock', drawDiscard: 'Take the top discard',
    discardLocked: 'You cannot use this card now', empty: 'empty',
    opened: 'opened', notOpened: 'not opened', youOpened: 'You have opened', needOpen: 'Opening: at least 40 points in one go',
    mustUse: 'You must put this card on the table this turn:', drawFirst: 'Draw a card: click the stock or the discard pile.',
    tableEmpty: 'No melds on the table yet.', owner: 'by {name}',
    attach: 'Attach', attachAria: 'Attach the selected cards to this meld', swap: 'Swap joker', swapAria: 'Swap the joker in this meld for the selected card',
    newGroup: '＋ Group', newGroupAria: 'Make a group from the selected cards', meld: 'Lay down', discardBtn: 'Discard',
    suggest: '💡 Use suggestion', clear: 'Clear', remove: 'Remove this group',
    pts: '{n} pts', invalid: 'not a meld', selection: 'Selection', staged: 'Your melds',
    total: 'Total {n} / 40', totalOpen: 'Total {n}', keepOne: 'Keep at least one card to discard',
    selectHint: 'Select cards, then attach them to a meld, group them, or discard one (double-click discards too).',
    penalties: 'Penalty points left in hand', winner: 'Winner', draw: 'Draw', stockEnd: 'The stock ran out: lowest penalty wins.',
    workspace: 'The table (your working copy)', reset: 'Reset', play: 'Play', drawM: 'Draw', pass: 'Pass',
    moveHere: 'Move selected cards here', newGroupSlot: '＋ New group', toHand: '↩ Back to hand',
    ok: 'valid', bad: 'invalid', fromHand: 'from your hand', placed: 'From your hand: {n}',
    mHint: 'Select cards (from your hand or the table), then tap a group or “New group”. On a computer you can also drag them.',
    mNeedValid: 'Every group must be valid', mNeedCard: 'Add at least one card from your hand',
    stockLeft: '{n} in stock', passes: 'Passes in a row: {n}', cardsLeft: 'Cards left', pointsLeft: 'Points',
    yourHand: 'Your hand', meldGroup: 'Meld {n}',
  },
  it: {
    sortSuit: 'Ordina: seme', sortRank: 'Ordina: valore', sortAria: 'Cambia l’ordine della tua mano',
    stock: 'Tallone', discard: 'Scarti', drawStock: 'Pesca dal tallone', drawDiscard: 'Prendi lo scarto in cima',
    discardLocked: 'Ora non puoi usare questa carta', empty: 'vuoto',
    opened: 'aperto', notOpened: 'non aperto', youOpened: 'Hai aperto', needOpen: 'Apertura: almeno 40 punti in una volta',
    mustUse: 'Devi calare questa carta in questo turno:', drawFirst: 'Pesca una carta: tocca il tallone o gli scarti.',
    tableEmpty: 'Ancora nessuna combinazione in tavola.', owner: 'di {name}',
    attach: 'Attacca', attachAria: 'Attacca le carte selezionate a questa combinazione', swap: 'Scambia jolly', swapAria: 'Scambia il jolly di questa combinazione con la carta selezionata',
    newGroup: '＋ Gruppo', newGroupAria: 'Fai un gruppo con le carte selezionate', meld: 'Cala', discardBtn: 'Scarta',
    suggest: '💡 Usa il suggerimento', clear: 'Svuota', remove: 'Togli questo gruppo',
    pts: '{n} punti', invalid: 'non valida', selection: 'Selezione', staged: 'Le tue calate',
    total: 'Totale {n} / 40', totalOpen: 'Totale {n}', keepOne: 'Tieni almeno una carta da scartare',
    selectHint: 'Seleziona le carte, poi attaccale a una combinazione, raggruppale o scartane una (anche col doppio clic).',
    penalties: 'Punti di penalità rimasti in mano', winner: 'Vince', draw: 'Pareggio', stockEnd: 'Il tallone è finito: vince la penalità più bassa.',
    workspace: 'Il tavolo (la tua copia di lavoro)', reset: 'Annulla', play: 'Gioca', drawM: 'Pesca', pass: 'Passa',
    moveHere: 'Sposta qui le carte selezionate', newGroupSlot: '＋ Nuovo gruppo', toHand: '↩ Torna in mano',
    ok: 'valido', bad: 'non valido', fromHand: 'dalla tua mano', placed: 'Dalla tua mano: {n}',
    mHint: 'Seleziona le carte (dalla mano o dal tavolo), poi tocca un gruppo o “Nuovo gruppo”. Al computer puoi anche trascinarle.',
    mNeedValid: 'Ogni gruppo deve essere valido', mNeedCard: 'Aggiungi almeno una carta dalla mano',
    stockLeft: '{n} nel tallone', passes: 'Passi di fila: {n}', cardsLeft: 'Carte rimaste', pointsLeft: 'Punti',
    yourHand: 'La tua mano', meldGroup: 'Combinazione {n}',
  },
  fr: {
    sortSuit: 'Trier : couleur', sortRank: 'Trier : valeur', sortAria: 'Changer le tri de votre main',
    stock: 'Pioche', discard: 'Défausse', drawStock: 'Piocher', drawDiscard: 'Prendre la carte de la défausse',
    discardLocked: 'Vous ne pouvez pas utiliser cette carte maintenant', empty: 'vide',
    opened: 'ouvert', notOpened: 'pas ouvert', youOpened: 'Vous avez ouvert', needOpen: 'Ouverture : au moins 40 points en une fois',
    mustUse: 'Vous devez poser cette carte ce tour-ci :', drawFirst: 'Piochez une carte : touchez la pioche ou la défausse.',
    tableEmpty: 'Aucune combinaison sur la table.', owner: 'de {name}',
    attach: 'Ajouter', attachAria: 'Ajouter les cartes sélectionnées à cette combinaison', swap: 'Échanger le joker', swapAria: 'Échanger le joker de cette combinaison contre la carte sélectionnée',
    newGroup: '＋ Groupe', newGroupAria: 'Faire un groupe avec les cartes sélectionnées', meld: 'Poser', discardBtn: 'Défausser',
    suggest: '💡 Utiliser la suggestion', clear: 'Vider', remove: 'Retirer ce groupe',
    pts: '{n} pts', invalid: 'pas valide', selection: 'Sélection', staged: 'Vos combinaisons',
    total: 'Total {n} / 40', totalOpen: 'Total {n}', keepOne: 'Gardez au moins une carte à défausser',
    selectHint: 'Sélectionnez des cartes, puis ajoutez-les à une combinaison, groupez-les ou défaussez-en une (double-clic aussi).',
    penalties: 'Points de pénalité restés en main', winner: 'Gagnant', draw: 'Égalité', stockEnd: 'La pioche est épuisée : la plus petite pénalité gagne.',
    workspace: 'La table (votre copie de travail)', reset: 'Annuler', play: 'Jouer', drawM: 'Piocher', pass: 'Passer',
    moveHere: 'Déplacer ici les cartes sélectionnées', newGroupSlot: '＋ Nouveau groupe', toHand: '↩ Retour en main',
    ok: 'valide', bad: 'pas valide', fromHand: 'de votre main', placed: 'De votre main : {n}',
    mHint: 'Sélectionnez des cartes (main ou table), puis touchez un groupe ou « Nouveau groupe ». À l’ordinateur, vous pouvez aussi les glisser.',
    mNeedValid: 'Chaque groupe doit être valide', mNeedCard: 'Ajoutez au moins une carte de votre main',
    stockLeft: '{n} dans la pioche', passes: 'Passes d’affilée : {n}', cardsLeft: 'Cartes restantes', pointsLeft: 'Points',
    yourHand: 'Votre main', meldGroup: 'Combinaison {n}',
  },
});

const DECK = 'fr';
const STATE = new Map(); // table id -> UI state

// --- melds (same rules as src/marione/games/melds.py) --------------------------------------------
const RANKS = '23456789TJQKA';
const SUITS = 'shdc';
const SHOW_SUITS = 'shcd'; // alternate colours in the hand
const isJ = (c) => c[0] === 'X';
const posRank = (p) => (p === 1 || p === 14 ? 'A' : RANKS[p - 2]);
const setVal = (r) => (r === 'A' ? 11 : 'TJQK'.includes(r) ? 10 : Number(r));
const runVal = (p) => (p === 1 ? 1 : p === 14 ? 11 : Math.min(p, 10));

export function analyse(cards, jokers = true) {
  if (cards.length < 3) return null;
  const wild = cards.filter(isJ);
  const real = cards.filter((c) => !isJ(c));
  if (wild.length && !jokers) return null;
  if (wild.length > 1 || real.length < 2) return null;
  return asSet(real, wild) || asRun(real, wild);
}

function asSet(real, wild) {
  const r = real[0][0];
  if (real.some((c) => c[0] !== r)) return null;
  const suits = real.map((c) => c[1]);
  if (new Set(suits).size !== suits.length || real.length + wild.length > 4) return null;
  const ordered = [...real].sort((a, b) => SUITS.indexOf(a[1]) - SUITS.indexOf(b[1]));
  return { kind: 'set', cards: [...ordered, ...wild], points: setVal(r) * (real.length + wild.length) };
}

function asRun(real, wild) {
  const s = real[0][1];
  if (real.some((c) => c[1] !== s) || real.length + wild.length > 13) return null;
  const ranks = real.map((c) => c[0]);
  if (new Set(ranks).size !== ranks.length) return null;
  for (const ace of ranks.includes('A') ? [1, 14] : [0]) {
    const posOf = (c) => (c[0] === 'A' ? ace : RANKS.indexOf(c[0]) + 2);
    const sorted = [...real].sort((a, b) => posOf(a) - posOf(b));
    const pos = sorted.map(posOf);
    const lo = pos[0], hi = pos[pos.length - 1];
    const gaps = [];
    for (let p = lo; p <= hi; p++) if (!pos.includes(p)) gaps.push(p);
    if (gaps.length > wild.length) continue;
    const extra = wild.length - gaps.length;
    const at = [...gaps];
    if (extra) {
      if (hi + extra <= 14 && !(ace === 1 && hi + extra === 14)) for (let p = hi + 1; p <= hi + extra; p++) at.push(p);
      else if (lo - extra >= 1 && !(ace === 14 && lo - extra === 1)) for (let p = lo - extra; p < lo; p++) at.push(p);
      else continue;
    }
    const byPos = new Map(pos.map((p, i) => [p, sorted[i]]));
    at.forEach((p, i) => byPos.set(p, wild[i]));
    const order = [...byPos.keys()].sort((a, b) => a - b);
    return { kind: 'run', cards: order.map((p) => byPos.get(p)), points: order.reduce((n, p) => n + runVal(p), 0) };
  }
  return null;
}

/** Can `c` take the joker's place in `cards` (scala 40 swap)? */
function swapOk(cards, c) {
  if (isJ(c) || !cards.some(isJ)) return false;
  return analyse(cards.map((x) => (isJ(x) ? c : x)), false) != null;
}

// --- shared bits ----------------------------------------------------------------------------------
const rankKey = (c) => (isJ(c) ? 99 : RANKS.indexOf(c[0]));
const suitKey = (c) => (isJ(c) ? 9 : SHOW_SUITS.indexOf(c[1]));
function sortIdx(hand, by) {
  const idx = hand.map((_, i) => i);
  const k = by === 'rank'
    ? (i) => [rankKey(hand[i]), suitKey(hand[i]), i]
    : (i) => [suitKey(hand[i]), rankKey(hand[i]), i];
  return idx.sort((a, b) => { const x = k(a), y = k(b); return x[0] - y[0] || x[1] - y[1] || x[2] - y[2]; });
}
const sortCodes = (codes) => [...codes].sort((a, b) => suitKey(a) - suitKey(b) || rankKey(a) - rankKey(b));

/** Cards in `hand` that were not in `prev` (as multisets): the ones just drawn. */
function freshIdx(hand, prev) {
  if (!prev) return new Set();
  const left = {};
  for (const c of prev) left[c] = (left[c] || 0) + 1;
  const out = new Set();
  hand.forEach((c, i) => { if (left[c]) left[c] -= 1; else out.add(i); });
  return out;
}

function sortToggle(L, rerender) {
  return h('button', { type: 'button', class: 'btn ghost sm rm-sort', 'aria-label': tr('sortAria'),
    onclick: () => { L.sortBy = L.sortBy === 'rank' ? 'suit' : 'rank'; rerender(); } },
  L.sortBy === 'rank' ? tr('sortRank') : tr('sortSuit'));
}

/** A row of overlapping cards (a meld on the table). */
function meldCards(codes, size, cls) {
  return h('div', { class: 'rm-cards ' + (size || 'sm') + (cls ? ' ' + cls : '') }, codes.map((c) => card(c, { deck: DECK, size: size || 'sm' })));
}

const btn = (label, cls, props) => h('button', { type: 'button', class: 'btn ' + cls, ...props }, label);

export function render(el, tb, ctx) {
  // UI state per table. Kept at module level as well as in ctx.local: the page can remount the
  // table view (and hand us a fresh ctx.local) on any store refresh.
  if (!STATE.has(tb.id)) STATE.set(tb.id, ctx.local.rm || {});
  const L = STATE.get(tb.id);
  ctx.local.rm = L;
  L.sortBy ||= 'suit';
  // the page re-renders on every poll; skip identical updates so a click in progress is not lost
  const stamp = tb.id + ':' + tb.version + ':' + tb.status;
  if (L.stamp === stamp && L.el === el && el.childElementCount) return;
  L.stamp = stamp; L.el = el;
  if (tb.game === 'machiavelli') machiavelli(el, tb, ctx, L);
  else scala40(el, tb, ctx, L);
}

// ==================================================================================================
// scala 40
// ==================================================================================================
function scala40(el, tb, ctx, L) {
  const st = tb.state;
  const rerender = () => scala40(el, tb, ctx, L);
  const hand = st.hand || [];
  const me = tb.you;
  const mine = tb.status === 'playing' && tb.toAct.includes(me);
  const play = mine && st.phase === 'play';
  const legal = tb.legal || [];

  // reset the selection when the hand changes (draws, melds, a new match)
  const sig = tb.id + '|' + hand.join(',') + '|' + st.phase + '|' + st.table.length;
  if (L.sig !== sig) {
    L.fresh = L.sig && L.hand ? freshIdx(hand, L.hand) : new Set();
    L.newMelds = L.tableLen != null && st.table.length > L.tableLen ? L.tableLen : st.table.length;
    L.sig = sig; L.hand = [...hand]; L.tableLen = st.table.length;
    L.sel = new Set(); L.staged = [];
  }
  const staged = new Set(L.staged.flat());
  const selIdx = [...L.sel].filter((i) => i < hand.length && !staged.has(i));
  const selCards = selIdx.map((i) => hand[i]);
  const opened = me != null && st.opened[me];
  const canDiscard = legal.some((a) => a.type === 'discard');
  const suggested = legal.find((a) => a.type === 'meld' && a.suggested);
  const canDrawStock = legal.some((a) => a.type === 'draw' && a.from === 'stock');
  const canDrawDiscard = legal.some((a) => a.type === 'draw' && a.from === 'discard');

  // --- stock & discard
  const stockEl = canDrawStock
    ? h('button', { type: 'button', class: 'rm-pile click', 'aria-label': tr('drawStock'), onclick: (e) => ctx.act({ type: 'draw', from: 'stock' }, e.currentTarget) },
      card('??', { deck: DECK, size: 'md' }), h('span', { class: 'pile-n' }, String(st.stock)))
    : h('span', { class: 'rm-pile' }, card('??', { deck: DECK, size: 'md' }), h('span', { class: 'pile-n' }, String(st.stock)));
  const top = st.discardTop;
  const discardEl = !top
    ? h('span', { class: 'rm-pile rm-empty' }, tr('empty'))
    : canDrawDiscard
      ? h('button', { type: 'button', class: 'rm-pile click', 'aria-label': tr('drawDiscard') + ': ' + cardName(top, DECK), onclick: (e) => ctx.act({ type: 'draw', from: 'discard' }, e.currentTarget) },
        card(top, { deck: DECK, size: 'md' }), h('span', { class: 'pile-n' }, String(st.discardCount)))
      : h('span', { class: 'rm-pile' + (mine && st.phase === 'draw' ? ' locked' : ''), title: mine && st.phase === 'draw' ? tr('discardLocked') : null },
        card(top, { deck: DECK, size: 'md' }), h('span', { class: 'pile-n' }, String(st.discardCount)));

  const info = h('div', { class: 'rm-info' },
    me != null && tb.status === 'playing' ? h('p', { class: 'rm-open' + (opened ? 'yes' : 'no') }, opened ? '✓ ' + tr('youOpened') : tr('needOpen')) : null,
    st.mustUse ? h('div', { class: 'rm-must', role: 'status' }, h('span', null, tr('mustUse')), card(st.mustUse, { deck: DECK, size: 'sm' })) : null,
    mine && st.phase === 'draw' ? h('p', { class: 'hint' }, tr('drawFirst')) : null);

  const middle = h('div', { class: 'rm-mid' },
    h('div', { class: 'rm-piles' },
      h('figure', { class: 'rm-pilebox' }, stockEl, h('figcaption', null, tr('stock'))),
      h('figure', { class: 'rm-pilebox' }, discardEl, h('figcaption', null, tr('discard')))),
    info);

  // --- table melds (attach / swap targets for the current selection)
  const leavesOne = selIdx.length > 0 && selIdx.length + staged.size < hand.length;
  const tableEl = h('div', { class: 'rm-table', 'aria-label': tr('workspace') },
    st.table.length ? st.table.map((m, i) => {
      const attach = play && opened && leavesOne && analyse([...m.cards, ...selCards]) != null;
      const swap = play && opened && selCards.length === 1 && swapOk(m.cards, selCards[0]);
      return h('div', { class: 'rm-meld' + (attach || swap ? ' target' : '') + (i >= L.newMelds ? ' fresh' : '') },
        meldCards(m.cards, 'sm'),
        h('div', { class: 'rm-meld-foot' },
          h('small', null, tr('owner', { name: ctx.name(m.owner) })),
          attach ? btn('＋ ' + tr('attach'), 'sm primary', { 'aria-label': tr('attachAria'), onclick: (e) => ctx.act({ type: 'layoff', meld: i, cards: selCards }, e.currentTarget) }) : null,
          swap ? btn('⇄ ' + tr('swap'), 'sm coin', { 'aria-label': tr('swapAria'), onclick: (e) => ctx.act({ type: 'swap_joker', meld: i, card: selCards[0] }, e.currentTarget) }) : null));
    }) : h('p', { class: 'muted rm-none' }, tr('tableEmpty')));

  // --- staging: groups + the live selection
  let staging = null;
  if (play) {
    const groups = L.staged.map((g) => g.map((i) => hand[i]));
    const infos = groups.map((g) => analyse(g));
    const selInfo = selCards.length >= 3 ? analyse(selCards) : null;
    const sending = [...groups, ...(selInfo ? [selCards] : [])];
    const total = infos.reduce((n, m) => n + (m ? m.points : 0), 0) + (selInfo ? selInfo.points : 0);
    const used = staged.size + (selInfo ? selCards.length : 0);
    const allOk = infos.every(Boolean);
    const okToSend = sending.length > 0 && allOk && used < hand.length && (opened || total >= 40);
    const groupRow = (codes, m, onRemove, label) => h('div', { class: 'rm-stage-g ' + (m ? 'ok' : 'bad') },
      meldCards(m ? m.cards : codes, 'sm'),
      h('span', { class: 'rm-badge' }, label ? label + ' · ' : '', m ? tr('pts', { n: m.points }) : tr('invalid')),
      onRemove ? h('button', { type: 'button', class: 'icon-btn rm-x', 'aria-label': tr('remove'), onclick: onRemove }, '✕') : null);
    staging = h('div', { class: 'rm-stage' },
      groups.length || selCards.length > 1 ? h('div', { class: 'rm-stage-list' },
        groups.map((g, k) => groupRow(g, infos[k], () => { L.staged.splice(k, 1); rerender(); })),
        selCards.length > 1 ? groupRow(sortCodes(selCards), selCards.length >= 3 ? selInfo : null, null, tr('selection')) : null) : null,
      h('div', { class: 'rm-stage-bar' },
        h('span', { class: 'rm-total' + (!opened ? (total >= 40 ? ' ok' : ' short') : '') }, opened ? tr('totalOpen', { n: total }) : tr('total', { n: total })),
        used >= hand.length && sending.length ? h('span', { class: 'rm-warn' }, tr('keepOne')) : null,
        h('span', { class: 'rm-sp' }),
        suggested ? btn(tr('suggest'), 'sm ghost', { onclick: () => {
          const pool = hand.map((c, i) => [c, i]);
          const taken = new Set();
          L.staged = suggested.suggested.map((g) => g.map((c) => { const p = pool.find(([x, i]) => x === c && !taken.has(i)); taken.add(p[1]); return p[1]; }));
          L.sel = new Set(); rerender();
        } }) : null,
        btn(tr('newGroup'), 'sm', { 'aria-label': tr('newGroupAria'), disabled: selIdx.length < 1, onclick: () => { L.staged.push(selIdx); L.sel = new Set(); rerender(); } }),
        groups.length ? btn(tr('clear'), 'sm ghost', { onclick: () => { L.staged = []; rerender(); } }) : null,
        btn('✓ ' + tr('meld'), 'sm primary', { disabled: !okToSend, onclick: (e) => ctx.act({ type: 'meld', melds: sending }, e.currentTarget) }),
        btn('🗑 ' + tr('discardBtn'), 'sm danger', { disabled: !(canDiscard && selIdx.length === 1 && !L.staged.length), onclick: (e) => ctx.act({ type: 'discard', card: selCards[0] }, e.currentTarget) })),
      h('p', { class: 'hint rm-tip' }, tr('selectHint')));
  }

  // --- hand
  const handEl = me != null ? h('div', { class: 'rm-handbox' },
    h('div', { class: 'rm-handhead' }, h('strong', null, tr('yourHand') + ' · ' + hand.length), sortToggle(L, rerender)),
    h('div', { class: 'rm-hand', role: 'group', 'aria-label': tr('yourHand') }, sortIdx(hand, L.sortBy).map((i) => {
      const c = hand[i];
      const isStaged = staged.has(i);
      const b = card(c, { deck: DECK, size: 'md', selected: L.sel.has(i) && !isStaged, disabled: isStaged,
        cls: (st.mustUse === c ? 'rm-mustc' : '') + (L.fresh.has(i) ? ' rm-fresh' : '') + (isStaged ? ' rm-staged' : ''),
        onClick: isStaged ? null : () => { if (L.sel.has(i)) L.sel.delete(i); else L.sel.add(i); rerender(); } });
      if (play && canDiscard && !isStaged) {
        b.addEventListener('dblclick', () => { if (!L.staged.length) ctx.act({ type: 'discard', card: c }); });
      }
      return b;
    }))) : null;

  fill(el, felt('rm-felt rm-scala',
    opponents(tb, ctx, DECK, st.handCounts, (i) => h('span', { class: 'tag rm-tag ' + (st.opened[i] ? 'yes' : 'no') }, st.opened[i] ? '✓ ' + tr('opened') : tr('notOpened'))),
    middle,
    tableEl,
    turnBanner(tb, ctx),
    staging,
    handEl),
  scalaEnd(tb, st, ctx));
  L.newMelds = Infinity; // animate new melds / drawn cards once, not on every click
  L.fresh = new Set();
}

function scalaEnd(tb, st, ctx) {
  if (tb.status !== 'over' || !st.penalties) return null;
  const r = tb.result || {};
  const hands = r.hands || [];
  return h('div', { class: 'card end-box rm-end' },
    h('h3', null, st.winner != null ? '🏆 ' + tr('winner') + ': ' + ctx.name(st.winner) : tr('draw')),
    r.reason === 'stock' ? h('p', { class: 'hint' }, tr('stockEnd')) : null,
    h('p', { class: 'rm-end-sub' }, tr('penalties')),
    h('ul', null, tb.seats.map((_, i) => h('li', { class: i === st.winner ? 'win' : '' },
      h('span', null, ctx.name(i)),
      hands[i] && hands[i].length ? h('span', { class: 'rm-end-hand' }, hands[i].map((c) => card(c, { deck: DECK, size: 'xs' }))) : null,
      h('b', null, String(st.penalties[i]))))));
}

// ==================================================================================================
// machiavelli
// ==================================================================================================
function machiavelli(el, tb, ctx, L) {
  const st = tb.state;
  const rerender = () => machiavelli(el, tb, ctx, L);
  const hand = st.hand || [];
  const me = tb.you;
  const mine = tb.status === 'playing' && tb.toAct.includes(me);

  // the workspace: ids "t<n>" for table cards, "h<i>" for hand cards; rebuilt when the real table changes
  const key = tb.id + '|' + JSON.stringify(st.table) + '|' + hand.join(',') + '|' + st.turn + '|' + tb.status;
  if (L.mkey !== key) {
    L.fresh = L.mkey && L.hand ? freshIdx(hand, L.hand) : new Set();
    L.mkey = key; L.hand = [...hand];
    const codes = {};
    let n = 0;
    const groups = st.table.map((g) => g.map((c) => { const id = 't' + n++; codes[id] = c; return id; }));
    hand.forEach((c, i) => { codes['h' + i] = c; });
    L.ws = { codes, groups };
    L.msel = new Set();
  }
  const ws = L.ws;
  const code = (id) => ws.codes[id];
  const inGroups = new Set(ws.groups.flat());
  const handLeft = hand.map((_, i) => 'h' + i).filter((id) => !inGroups.has(id));
  const placed = ws.groups.flat().filter((id) => id[0] === 'h').length;
  const checks = ws.groups.map((g) => analyse(g.map(code), false));
  const allOk = checks.every(Boolean);
  const canPlay = mine && allOk && placed > 0;

  const move = (ids, dest) => {
    // dest: group index, 'new' or 'hand'
    const moving = dest === 'hand' ? ids.filter((id) => id[0] === 'h') : ids;
    if (!moving.length) return;
    const set = new Set(moving);
    let target = dest === 'new' || dest === 'hand' ? null : ws.groups[dest];
    ws.groups = ws.groups.map((g) => {
      const kept = g.filter((id) => !set.has(id));
      if (g === target) target = kept;
      return kept;
    });
    if (dest === 'new') ws.groups.push([...moving]);
    else if (target) target.push(...moving);
    ws.groups = ws.groups.filter((g) => g.length);
    L.msel = new Set();
    rerender();
  };
  const toggle = (id) => { if (L.msel.has(id)) L.msel.delete(id); else L.msel.add(id); rerender(); };
  const selected = [...L.msel];
  const anySel = mine && selected.length > 0;

  const cardEl = (id, size, extraCls) => {
    const c = code(id);
    const fromHand = id[0] === 'h';
    const b = card(c, { deck: DECK, size, selected: L.msel.has(id), onClick: mine ? () => toggle(id) : null,
      cls: (fromHand && size === 'sm' ? 'rm-fromhand' : '') + (extraCls ? ' ' + extraCls : ''),
      label: cardName(c, DECK) + (fromHand && size === 'sm' ? ' (' + tr('fromHand') + ')' : '') });
    if (mine) dragify(b, id, L, move);
    return b;
  };

  const groupView = (g, k) => {
    const m = checks[k];
    const ordered = m ? orderIds(g, m.cards, code) : [...g].sort((a, b) => suitKey(code(a)) - suitKey(code(b)) || rankKey(code(a)) - rankKey(code(b)));
    const changed = g.some((id) => id[0] === 'h');
    return h('div', { class: 'rm-grp ' + (m ? 'ok' : 'bad') + (changed ? ' touched' : '') + (anySel ? ' target' : ''), 'data-drop': String(k),
      onclick: (e) => { if (anySel && e.target === e.currentTarget) move(selected, k); } },
    h('div', { class: 'rm-cards sm' }, ordered.map((id) => cardEl(id, 'sm'))),
    h('div', { class: 'rm-meld-foot' },
      mine ? h('span', { class: 'rm-badge ' + (m ? 'ok' : 'bad') }, m ? '✓ ' + tr('ok') : '✕ ' + tr('bad')) : null,
      anySel ? h('button', { type: 'button', class: 'btn sm primary rm-here', 'aria-label': tr('moveHere'), onclick: () => move(selected, k) }, '⤵') : null));
  };

  const tableEl = h('div', { class: 'rm-table rm-ws' + (mine ? ' mine' : ''), 'aria-label': tr('workspace') },
    ws.groups.length ? ws.groups.map(groupView) : !mine ? h('p', { class: 'muted rm-none' }, tr('tableEmpty')) : null,
    mine ? h('button', { type: 'button', class: 'rm-newgrp' + (anySel ? ' target' : ''), 'data-drop': 'new', disabled: !anySel || null,
      onclick: () => move(selected, 'new') }, tr('newGroupSlot')) : null);

  const handSorted = sortIdx(hand, L.sortBy).map((i) => 'h' + i).filter((id) => !inGroups.has(id));
  const selFromHandOnTable = selected.some((id) => id[0] === 'h' && inGroups.has(id));
  const handEl = me != null ? h('div', { class: 'rm-handbox' + (selFromHandOnTable ? ' target' : ''), 'data-drop': 'hand' },
    h('div', { class: 'rm-handhead' }, h('strong', null, tr('yourHand') + ' · ' + handLeft.length), sortToggle(L, rerender),
      selFromHandOnTable ? btn(tr('toHand'), 'sm ghost', { onclick: () => move(selected, 'hand') }) : null),
    h('div', { class: 'rm-hand', role: 'group', 'aria-label': tr('yourHand') },
      handSorted.map((id) => cardEl(id, 'md', L.fresh.has(Number(id.slice(1))) ? 'rm-fresh' : '')))) : null;

  const bar = mine ? h('div', { class: 'rm-stage-bar rm-mbar' },
    h('span', { class: 'rm-total' + (placed ? ' ok' : '') }, tr('placed', { n: placed })),
    !allOk ? h('span', { class: 'rm-warn' }, tr('mNeedValid')) : !placed ? h('span', { class: 'hint' }, tr('mNeedCard')) : null,
    h('span', { class: 'rm-sp' }),
    btn('↺ ' + tr('reset'), 'sm ghost', { onclick: () => { L.mkey = null; rerender(); } }),
    btn(st.stock ? '🂠 ' + tr('drawM') : tr('pass'), 'sm', { disabled: placed > 0, onclick: (e) => ctx.act({ type: 'draw' }, e.currentTarget) }),
    btn('✓ ' + tr('play'), 'sm primary', { disabled: !canPlay,
      onclick: (e) => ctx.act({ type: 'play', table: ws.groups.map((g) => g.map(code)) }, e.currentTarget) })) : null;

  fill(el, felt('rm-felt rm-machi',
    opponents(tb, ctx, DECK, st.handCounts),
    h('div', { class: 'rm-mid rm-mid-m' },
      h('figure', { class: 'rm-pilebox' }, h('span', { class: 'rm-pile' }, card('??', { deck: DECK, size: 'md' }), h('span', { class: 'pile-n' }, String(st.stock))),
        h('figcaption', null, tr('stock'))),
      h('div', { class: 'rm-info' },
        st.passes ? h('p', { class: 'hint' }, tr('passes', { n: st.passes })) : null,
        mine ? h('p', { class: 'hint rm-tip' }, tr('mHint')) : null)),
    tableEl,
    turnBanner(tb, ctx),
    bar,
    handEl),
  machiEnd(tb, ctx));
  L.fresh = new Set();
}

/** Ids of a group in the meld's display order (codes repeat: match each code once). */
function orderIds(ids, codes, code) {
  const pool = [...ids];
  return codes.map((c) => { const k = pool.findIndex((id) => code(id) === c); return pool.splice(k, 1)[0]; });
}

/** Mouse/pen drag & drop onto [data-drop] (touch uses tap-select then tap-destination). */
function dragify(b, id, L, move) {
  b.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'touch' || e.button !== 0) return;
    e.preventDefault(); // no text selection while dragging
    const x0 = e.clientX, y0 = e.clientY;
    let ghost = null, over = null;
    const ids = L.msel.has(id) ? [...L.msel] : [id];
    const onMove = (ev) => {
      if (!ghost) {
        if (Math.hypot(ev.clientX - x0, ev.clientY - y0) < 6) return;
        ghost = b.cloneNode(true);
        ghost.classList.add('rm-ghost');
        if (ids.length > 1) ghost.append(Object.assign(document.createElement('span'), { className: 'pile-n', textContent: String(ids.length) }));
        document.body.append(ghost);
        b.classList.add('rm-dragging');
      }
      ghost.style.left = ev.clientX - 26 + 'px';
      ghost.style.top = ev.clientY - 40 + 'px';
      const t = document.elementFromPoint(ev.clientX, ev.clientY);
      const zone = t && t.closest('[data-drop]');
      if (zone !== over) { if (over) over.classList.remove('rm-over'); over = zone; if (over) over.classList.add('rm-over'); }
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (!ghost) return;
      ghost.remove();
      b.classList.remove('rm-dragging');
      // swallow the click that follows the drag
      const swallow = (ce) => { ce.stopPropagation(); ce.preventDefault(); };
      window.addEventListener('click', swallow, { capture: true, once: true });
      setTimeout(() => window.removeEventListener('click', swallow, true), 0);
      if (over) {
        over.classList.remove('rm-over');
        const d = over.dataset.drop;
        move(ids, d === 'new' || d === 'hand' ? d : Number(d));
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  });
}

function machiEnd(tb, ctx) {
  if (tb.status !== 'over' || !tb.result) return null;
  const r = tb.result;
  if (!r.cards) return null;
  const win = new Set(r.winners || []);
  return h('div', { class: 'card end-box rm-end' },
    h('h3', null, win.size ? '🏆 ' + tr('winner') + ': ' + [...win].map((i) => ctx.name(i)).join(', ') : tr('draw')),
    h('ul', null, tb.seats.map((_, i) => h('li', { class: win.has(i) ? 'win' : '' },
      h('span', null, ctx.name(i)),
      h('span', { class: 'rm-end-sub' }, tr('cardsLeft') + ': ' + r.cards[i]),
      h('b', null, tr('pointsLeft') + ' ' + (r.points ? r.points[i] : 0))))));
}

export function destroy() {
  document.querySelectorAll('.rm-ghost').forEach((g) => g.remove());
}
