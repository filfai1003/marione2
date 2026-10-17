// Trick-taking games with Italian cards: briscola, tresette, bestia.
// The table: opponents around, the trick in the middle (with the briscola / trump and the deck),
// your hand at the bottom. Click a playable card to play it.
import { h, fill } from '../util.js';
import { card, pile } from '../art.js';
import { felt, opponents, handRow, trickView, turnBanner, legalCards } from './common.js';

const SUITS = { d: 'denari', c: 'coppe', b: 'bastoni', s: 'spade' };

export function render(el, tb, ctx) {
  const st = tb.state;
  const t = ctx.t;
  const playable = legalCards(tb);
  const deck = 'it';
  const sides = sidesOf(tb);

  // middle: trump/briscola + deck, the trick (or the last one, briefly), info
  const trumpCard = st.briscola || st.trump || null;
  const middle = h('div', { class: 'table-mid' },
    h('div', { class: 'mid-left' },
      st.deck != null || st.talon != null
        ? h('div', { class: 'deck-stack' }, (st.deck || st.talon) ? pile(deck, st.deck ?? st.talon, t('games.deckLeft')) : null,
          trumpCard ? h('div', { class: 'trump' }, card(trumpCard, { deck, size: 'md' }),
            h('small', null, tb.game === 'briscola' ? t('trick.briscola') : t('trick.trump'))) : null)
        : trumpCard ? h('div', { class: 'trump' }, card(trumpCard, { deck, size: 'md' }), h('small', null, t('trick.trump'))) : null),
    h('div', { class: 'mid-trick' },
      st.trick && st.trick.length ? trickView(st.trick, tb, ctx, deck)
        : st.lastTrick && st.lastTrick.length ? h('div', { class: 'last-trick' }, trickView(st.lastTrick, tb, ctx, deck),
          st.lastWinner != null ? h('small', null, t('trick.tookIt', { name: ctx.name(st.lastWinner) })) : null)
          : h('p', { class: 'muted small' }, st.leadSuit ? t('trick.lead', { suit: SUITS[st.leadSuit] }) : '')),
    h('div', { class: 'mid-right' }, scoreBox(tb, st, ctx, sides)));

  const drawn = st.drawn && st.drawn.length
    ? h('p', { class: 'drawn' }, t('trick.drawn') + ' ', st.drawn.map((d) => h('span', { class: 'drawn-one' }, ctx.name(d.seat) + ': ', card(d.card, { deck, size: 'xs' }))))
    : null;
  const accusi = st.accusi && st.accusi.length
    ? h('p', { class: 'hint' }, st.accusi.map((a) => `${ctx.name(a.seat)}: ${a.kind} (+${a.points})`).join(' · ')) : null;

  fill(el, felt('trick-felt',
    opponents(tb, ctx, deck, st.handCounts, (i) => st.tricks ? h('span', { class: 'tag counter' }, String(st.tricks[i])) : null),
    middle, drawn, accusi,
    turnBanner(tb, ctx),
    tb.you != null ? handRow(st.hand || [], {
      deck,
      playable: (c) => playable.has(c),
      onPick: (c) => ctx.act({ type: 'play', card: c }),
    }) : null),
  endBox(tb, st, ctx, sides));
}

/** Who scores together: teams in 2v2, otherwise each seat. */
function sidesOf(tb) {
  if (tb.teams && tb.teams.length) return tb.teams.map((tm) => tm);
  return tb.seats.map((_, i) => [i]);
}

function sideName(side, ctx) {
  return side.map((i) => ctx.name(i)).join(' + ');
}

function scoreBox(tb, st, ctx, sides) {
  const t = ctx.t;
  if (tb.game === 'bestia') {
    return h('div', { class: 'score-box' }, h('strong', null, t('trick.tricks')),
      h('ul', null, tb.seats.map((_, i) => h('li', null, h('span', null, ctx.name(i)), h('b', null, String(st.tricks ? st.tricks[i] : 0))))));
  }
  if (tb.game === 'tresette') {
    const pts = st.handPoints ? st.handPoints.points : [];
    return h('div', { class: 'score-box' }, h('strong', null, st.target ? t('trick.matchTo', { n: st.target }) : t('trick.score')),
      h('ul', null, sides.map((side, i) => h('li', null, h('span', null, sideName(side, ctx)),
        h('b', null, `${st.scores ? st.scores[i] : 0}`), h('small', null, ` (+${pts[i] ?? 0})`)))));
  }
  // briscola: cards taken so far (points are revealed at the end)
  return h('div', { class: 'score-box' }, h('strong', null, t('trick.taken')),
    h('ul', null, sides.map((side) => h('li', null, h('span', null, sideName(side, ctx)),
      h('b', null, String(side.reduce((n, i) => n + (st.taken ? st.taken[i] : 0), 0)))))));
}

function endBox(tb, st, ctx, sides) {
  const t = ctx.t;
  if (tb.status !== 'over') {
    if (tb.game === 'tresette' && st.lastHand) {
      return h('p', { class: 'hint center' }, t('trick.lastHand') + ' ' + sides.map((s, i) => `${sideName(s, ctx)} ${st.lastHand.points[i]}`).join(' · '));
    }
    return null;
  }
  const r = tb.result || {};
  if (tb.game === 'briscola' && r.points) {
    return h('div', { class: 'card end-box' }, h('h3', null, t('trick.finalPoints')),
      h('ul', null, sides.map((s, i) => h('li', null, h('span', null, sideName(s, ctx)), h('b', null, String(r.points[i]))))));
  }
  if (tb.game === 'tresette' && r.scores) {
    return h('div', { class: 'card end-box' }, h('h3', null, t('trick.finalScore')),
      h('ul', null, sides.map((s, i) => h('li', null, h('span', null, sideName(s, ctx)), h('b', null, String(r.scores[i]))))));
  }
  if (tb.game === 'bestia' && r.tricks) {
    return h('div', { class: 'card end-box' }, h('h3', null, t('trick.tricks')),
      h('ul', null, tb.seats.map((_, i) => h('li', null, h('span', null, ctx.name(i) + ((r.bestia || []).includes(i) ? ' 🐗 ' + t('trick.bestia') : '')),
        h('b', null, String(r.tricks[i]))))));
  }
  return null;
}
