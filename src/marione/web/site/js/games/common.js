// Pieces shared by the game renderers: the felt, opponents around it, the hand, the turn banner.
import { h } from '../util.js';
import { card } from '../art.js';
import { getLang } from '../i18n.js';

/**
 * Texts that belong to one renderer: local({en: {...}, it: {...}, fr: {...}}) returns tr(key, vars).
 * Every key must exist in all three languages.
 */
export function local(dict) {
  return (key, vars) => {
    const text = (dict[getLang()] || dict.en)[key] ?? dict.en[key] ?? key;
    return vars ? text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? '')) : text;
  };
}

export const felt = (cls, ...kids) => h('div', { class: 'felt ' + (cls || '') }, ...kids);

/** "Your turn" / "Waiting for Anna" (+ seconds left in multiplayer). */
export function turnBanner(tb, ctx, extra) {
  if (tb.status !== 'playing') return null;
  const mine = tb.toAct.includes(tb.you);
  const who = tb.toAct.map((i) => ctx.name(i)).join(', ');
  return h('p', { class: 'turn-banner' + (mine ? ' mine' : ''), role: 'status', 'aria-live': 'polite' },
    mine ? ctx.t('games.yourTurn') : ctx.t('games.waitingFor', { name: who }),
    tb.turnLeft != null ? h('span', { class: 'turn-left', 'data-turnleft': '' }, tb.turnLeft + 's') : null,
    extra || null);
}

/** Where a seat sits on screen relative to you: bottom (you), then clockwise. */
export function position(rel, n) {
  if (rel === 0) return 'bottom';
  if (n === 2) return 'top';
  if (n === 3) return rel === 1 ? 'left' : 'right';
  if (n === 4) return ['bottom', 'left', 'top', 'right'][rel];
  return 'top';
}

/** The other players: name, cards in hand (face down) and an optional badge. */
export function opponents(tb, ctx, deck, counts, badge) {
  const n = tb.seats.length;
  const others = [];
  for (let i = 0; i < n; i++) {
    if (i === tb.you) continue;
    const rel = ctx.rel(i);
    const cnt = counts ? counts[i] : 0;
    others.push(h('div', { class: 'opp pos-' + position(rel, n) + (tb.toAct.includes(i) ? ' turn' : '') },
      h('div', { class: 'opp-name' }, ctx.name(i), badge ? badge(i) : null),
      h('div', { class: 'opp-cards' }, Array.from({ length: Math.min(cnt, 13) }, () => card('??', { deck, size: 'xs' })),
        cnt > 13 ? h('span', { class: 'pile-n' }, String(cnt)) : null)));
  }
  return h('div', { class: 'opps n' + n }, others);
}

/** Your hand: playable cards are buttons, the others dimmed. */
export function handRow(cards, { deck, playable, selected, onPick, size = 'lg' }) {
  return h('div', { class: 'hand' }, cards.map((c, i) => {
    const can = playable ? playable(c, i) : false;
    return card(c, { deck, size, onClick: can && onPick ? () => onPick(c, i) : null, disabled: playable && !can,
      selected: selected ? selected(c, i) : false });
  }));
}

/** Cards on the table for a trick: each placed toward its player. */
export function trickView(trick, tb, ctx, deck) {
  const n = tb.seats.length;
  return h('div', { class: 'trick n' + n }, trick.map((p) =>
    h('div', { class: 'trick-card pos-' + position(ctx.rel(p.seat), n) }, card(p.card, { deck, size: 'md' }),
      h('small', null, ctx.name(p.seat)))));
}

export const legalCards = (tb) => new Set((tb.legal || []).filter((a) => a.card).map((a) => a.card));
