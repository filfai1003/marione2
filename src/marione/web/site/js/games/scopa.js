// Scopa (Italian cards): 1v1, 1v1v1, 2v2.
// Opponents around, the table cards in the middle (deck + scores aside), your hand at the bottom.
// Click a card: with one legal play it is played at once (its take flashes first); with several
// possible takes the candidates light up and you pick one (tap a table card or an option), then confirm.
import { h, fill } from '../util.js';
import { card, pile } from '../art.js';
import { felt, opponents, turnBanner, local, position } from './common.js';

const DECK = 'it';
const CATS = ['carte', 'denari', 'settebello', 'primiera', 'scope'];

const tr = local({
  en: {
    to: 'Match to {n}', handOf: 'Hand {n} of {m}', handNo: 'Hand {n}', deck: 'Deck', scope: 'scope', scopeHand: 'Scope this hand',
    played: '{name} played', took: 'and took', laid: 'on the table', choose: 'Choose what to take with {card}',
    take: 'Take', cancel: 'Cancel', option: 'Option {n}', scopa: 'SCOPA!', scopaBy: 'Scopa by {name}!',
    lastHand: 'Hand {n} result', carte: 'Cards', denari: 'Coins', settebello: 'Settebello', primiera: 'Primiera',
    scopeRow: 'Scope', total: 'Total', match: 'Match', captured: 'cards taken', empty: 'The table is empty',
    finalHand: 'Last hand', you: 'you', tapTable: 'Tap a lit table card or an option below.',
  },
  it: {
    to: 'Partita ai {n}', handOf: 'Mano {n} di {m}', handNo: 'Mano {n}', deck: 'Mazzo', scope: 'scope', scopeHand: 'Scope in questa mano',
    played: '{name} ha giocato', took: 'e ha preso', laid: 'in tavola', choose: 'Scegli cosa prendere con {card}',
    take: 'Prendi', cancel: 'Annulla', option: 'Presa {n}', scopa: 'SCOPA!', scopaBy: 'Scopa di {name}!',
    lastHand: 'Risultato mano {n}', carte: 'Carte', denari: 'Denari', settebello: 'Settebello', primiera: 'Primiera',
    scopeRow: 'Scope', total: 'Totale', match: 'Partita', captured: 'carte prese', empty: 'La tavola è vuota',
    finalHand: 'Ultima mano', you: 'tu', tapTable: 'Tocca una carta illuminata in tavola o una presa qui sotto.',
  },
  fr: {
    to: 'Partie en {n}', handOf: 'Manche {n} sur {m}', handNo: 'Manche {n}', deck: 'Talon', scope: 'scopes', scopeHand: 'Scopes de la manche',
    played: '{name} a joué', took: 'et a pris', laid: 'sur la table', choose: 'Choisis quoi prendre avec {card}',
    take: 'Prendre', cancel: 'Annuler', option: 'Prise {n}', scopa: 'SCOPA !', scopaBy: 'Scopa de {name} !',
    lastHand: 'Résultat manche {n}', carte: 'Cartes', denari: 'Deniers', settebello: 'Settebello', primiera: 'Primiera',
    scopeRow: 'Scopes', total: 'Total', match: 'Partie', captured: 'cartes prises', empty: 'La table est vide',
    finalHand: 'Dernière manche', you: 'toi', tapTable: 'Touche une carte éclairée sur la table ou une prise ci-dessous.',
  },
});

let timer = null;

/** Who scores together: teams in 2v2, otherwise each seat. */
function sidesOf(tb) {
  if (tb.teams && tb.teams.length) return tb.teams.map((tm) => tm);
  return tb.seats.map((_, i) => [i]);
}
const sideName = (side, ctx, tb) => side.map((i) => (i === tb.you ? ctx.name(i) + ' (' + tr('you') + ')' : ctx.name(i))).join(' + ');
const sameSet = (a, b) => a.length === b.length && a.every((c) => b.includes(c));

export function render(el, tb, ctx) {
  const st = tb.state;
  const L = ctx.local;
  const n = tb.seats.length;
  const sides = sidesOf(tb);
  const mine = tb.status === 'playing' && tb.toAct.includes(tb.you);
  const plays = (tb.legal || []).filter((a) => a.type === 'play');
  const optionsFor = (c) => plays.filter((a) => a.card === c);

  // selection only survives while it is still valid
  if (L.sel && (!mine || optionsFor(L.sel).length < 2)) { L.sel = null; L.opt = 0; }
  const opts = L.sel ? optionsFor(L.sel) : [];
  if (L.opt == null || L.opt >= opts.length) L.opt = 0;
  const cur = opts[L.opt] || null;
  const cand = new Set(opts.flatMap((o) => o.take));

  // a fresh last play (animate once)
  const lp = st.lastPlay;
  const key = lp ? `${st.handNo}:${st.deck}:${st.handCounts.join(',')}:${lp.seat}:${lp.card}` : `h${st.handNo}`;
  const fresh = L.lastKey !== key;
  L.lastKey = key;
  const isScopa = lp && lp.take.length > 0 && st.table.length === 0 && tb.status !== 'over';
  const handJustEnded = !lp && st.handResult && fresh && L.seenHand !== st.handNo;
  if (handJustEnded) L.seenHand = st.handNo;

  const pick = (o) => { L.opt = o; render(el, tb, ctx); };
  const tapTable = (c) => {
    const idx = opts.map((o, i) => [o, i]).filter(([o]) => o.take.includes(c)).map(([, i]) => i);
    if (!idx.length) return;
    const next = idx.find((i) => i > L.opt && idx.includes(i)) ?? idx[0];
    pick(cur && cur.take.includes(c) && idx.length > 1 ? next : idx[0]);
  };

  // --- the table cards ------------------------------------------------------------------
  const tableCards = h('div', { class: 'scp-table', 'aria-label': tr('deck') },
    st.table.length ? st.table.map((c) => {
      const isCand = cand.has(c);
      const isPick = cur && cur.take.includes(c);
      const cls = (isCand ? ' scp-cand' : '') + (isPick ? ' scp-pick' : '')
        + (fresh && lp && !lp.take.length && c === lp.card ? ' scp-laid scp-from-' + position(ctx.rel(lp.seat), n) : '');
      return h('div', { class: 'scp-tcard' + cls, 'data-tcard': c },
        isCand ? card(c, { deck: DECK, size: 'md', onClick: () => tapTable(c), selected: isPick }) : card(c, { deck: DECK, size: 'md' }));
    }) : h('p', { class: 'scp-empty' }, tr('empty')));

  // --- last play ----------------------------------------------------------------------------
  const last = lp ? h('div', { class: 'scp-last' + (fresh ? ' scp-fresh scp-from-' + position(ctx.rel(lp.seat), n) : ''), role: 'status', 'aria-live': 'polite' },
    h('span', { class: 'scp-last-who' }, tr('played', { name: ctx.name(lp.seat) })),
    h('span', { class: 'scp-last-card' }, card(lp.card, { deck: DECK, size: 'sm' })),
    lp.take.length
      ? [h('span', { class: 'scp-last-arrow' }, tr('took')), h('span', { class: 'scp-last-take' }, lp.take.map((c, i) =>
        h('span', { class: 'scp-took', style: { '--i': i } }, card(c, { deck: DECK, size: 'sm' }))))]
      : h('span', { class: 'scp-last-arrow' }, tr('laid'))) : null;

  // --- scores ---------------------------------------------------------------------------------
  const scoreBox = h('div', { class: 'score-box scp-score' },
    h('strong', null, st.hands ? tr('handOf', { n: st.handNo, m: st.hands }) : tr('to', { n: st.target })),
    !st.hands ? h('small', { class: 'scp-handno' }, tr('handNo', { n: st.handNo })) : null,
    h('ul', null, sides.map((side, i) => h('li', { class: side.includes(tb.you) ? 'scp-me' : null },
      h('span', null, sideName(side, ctx, tb)),
      st.scope[i] ? h('span', { class: 'scp-brooms', title: tr('scopeHand'), 'aria-label': `${st.scope[i]} ${tr('scope')}` }, '🧹×' + st.scope[i]) : null,
      h('b', null, String(st.scores[i]))))));

  const middle = h('div', { class: 'table-mid scp-mid' },
    h('div', { class: 'mid-left scp-deck' }, st.deck ? pile(DECK, st.deck, ctx.t('games.deckLeft')) : null,
      h('small', null, tr('deck') + ' ' + st.deck)),
    h('div', { class: 'scp-center' }, tableCards, last),
    h('div', { class: 'mid-right' }, scoreBox));

  // --- choosing a take ------------------------------------------------------------------------
  const chooser = opts.length > 1 ? h('div', { class: 'scp-choose' },
    h('p', { class: 'scp-choose-q' }, tr('choose', { card: '' }), card(L.sel, { deck: DECK, size: 'xs' })),
    h('small', { class: 'scp-choose-hint' }, tr('tapTable')),
    h('div', { class: 'scp-opts', role: 'radiogroup' }, opts.map((o, i) => h('button', {
      type: 'button', class: 'scp-opt' + (i === L.opt ? ' on' : ''), role: 'radio', 'aria-checked': i === L.opt ? 'true' : 'false',
      'aria-label': tr('option', { n: i + 1 }), onclick: () => pick(i),
    }, o.take.map((c) => card(c, { deck: DECK, size: 'xs' }))))),
    h('div', { class: 'scp-choose-btns' },
      h('button', { type: 'button', class: 'btn ghost sm', onclick: () => { L.sel = null; render(el, tb, ctx); } }, tr('cancel')),
      h('button', { type: 'button', class: 'btn primary sm', onclick: (e) => { const a = cur; L.sel = null; ctx.act({ type: 'play', card: a.card, take: a.take }, e.currentTarget); } }, tr('take')))) : null;

  // --- your hand ------------------------------------------------------------------------------
  const playableSet = new Set(plays.map((a) => a.card));
  const onPick = (c, btn) => {
    const o = optionsFor(c);
    if (o.length > 1) { L.sel = L.sel === c ? null : c; L.opt = 0; render(el, tb, ctx); return; }
    if (!o.length) return;
    // one play: flash what it takes, then play it
    L.sel = null;
    el.querySelectorAll('.scp-hand .pcard').forEach((b) => { b.disabled = true; });
    btn.classList.add('scp-going');
    o[0].take.forEach((t) => { const d = el.querySelector(`[data-tcard="${t}"]`); if (d) d.classList.add('scp-grab'); });
    const delay = o[0].take.length && !reduced() ? 380 : 0;
    clearTimeout(timer);
    timer = setTimeout(() => ctx.act({ type: 'play', card: c, take: o[0].take }), delay);
  };
  const hand = tb.you != null ? h('div', { class: 'hand scp-hand' }, (st.hand || []).map((c) => {
    const can = mine && playableSet.has(c);
    const b = card(c, { deck: DECK, size: 'lg', disabled: !can, selected: L.sel === c, onClick: can ? (e) => onPick(c, e.currentTarget) : null,
      cls: optionsFor(c).length > 1 && mine ? 'scp-multi' : '' });
    return b;
  })) : null;

  // --- the scopa burst --------------------------------------------------------------------------
  const burst = isScopa && fresh ? h('div', { class: 'scp-burst', role: 'status', 'aria-live': 'assertive' },
    h('span', { class: 'scp-burst-word' }, tr('scopa')), h('small', null, tr('scopaBy', { name: ctx.name(lp.seat) }))) : null;

  const badge = (i) => h('span', { class: 'tag counter scp-cap', title: tr('captured') }, '🂠 ' + st.captured[i]);

  fill(el,
    felt('scp-felt' + (mine ? ' scp-mine' : ''),
      opponents(tb, ctx, DECK, st.handCounts, badge),
      middle,
      chooser,
      turnBanner(tb, ctx),
      hand,
      tb.you != null ? h('p', { class: 'scp-mycap' }, '🂠 ' + st.captured[tb.you] + ' ' + tr('captured')) : null,
      burst),
    resultTable(tb, st, ctx, sides, handJustEnded || tb.status === 'over'));
}

function resultTable(tb, st, ctx, sides, hot) {
  const r = st.handResult;
  if (!r) return null;
  const doneNo = tb.status === 'over' ? st.handNo : st.handNo - 1;
  return h('section', { class: 'card scp-result' + (hot ? ' scp-hot' : '') },
    h('h3', null, tb.status === 'over' ? tr('finalHand') : tr('lastHand', { n: doneNo })),
    h('div', { class: 'scp-tablewrap' }, h('table', { class: 'scp-breakdown' },
      h('thead', null, h('tr', null, h('th', { scope: 'col' }, ''), sides.map((s) => h('th', { scope: 'col', class: s.includes(tb.you) ? 'scp-me' : null }, sideName(s, ctx, tb))))),
      h('tbody', null,
        CATS.map((k) => h('tr', null, h('th', { scope: 'row' }, tr(k === 'scope' ? 'scopeRow' : k)),
          r.map((row) => h('td', { class: row[k] ? 'scp-got' : null }, row[k] ? String(row[k]) : '·')))),
        h('tr', { class: 'scp-tot' }, h('th', { scope: 'row' }, tr('total')), r.map((row) => h('td', null, '+' + row.total))),
        h('tr', { class: 'scp-match' }, h('th', { scope: 'row' }, tr('match')), st.scores.map((s) => h('td', null, String(s))))))));
}

function reduced() {
  return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function destroy() { clearTimeout(timer); }
