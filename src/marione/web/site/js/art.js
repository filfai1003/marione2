// Marione's own artwork (made with Meshy, see scripts/art): icons and playing cards.
import { h } from './util.js';

/** An icon from img/icons (decorative unless a label is given). */
export function icon(name, size = 28, label = '') {
  return h('img', { class: 'ico', src: `img/icons/${name}.webp`, width: size, height: size, alt: label,
    'aria-hidden': label ? null : 'true', loading: 'lazy', decoding: 'async', draggable: 'false' });
}

const FR_NAMES = { s: 'spades', h: 'hearts', d: 'diamonds', c: 'clubs' };
const IT_NAMES = { d: 'denari', c: 'coppe', b: 'bastoni', s: 'spade' };
const FR_RANK = { T: '10', J: 'J', Q: 'Q', K: 'K', A: 'A' };
const IT_RANK = { 1: 'asso', F: 'fante', C: 'cavallo', R: 're' };

/** Readable card name for screen readers. */
export function cardName(code, deck) {
  if (!code || code === '??') return '?';
  if (code[0] === 'X') return 'joker';
  if (deck === 'it') return `${IT_RANK[code[0]] || code[0]} di ${IT_NAMES[code[1]] || code[1]}`;
  return `${FR_RANK[code[0]] || code[0]} of ${FR_NAMES[code[1]] || code[1]}`;
}

/** The back to show for a deck ("fr" follows the light/dark theme). */
export function backSrc(deck) {
  if (deck === 'it') return 'img/cards/it.webp';
  return document.documentElement.dataset.theme === 'dark' ? 'img/cards/fr_dark.webp' : 'img/cards/fr_light.webp';
}

/**
 * A card image. code "??" (or null) shows the back. Jokers are drawn in CSS.
 * opts: {deck: 'fr'|'it', size: 'sm'|'md'|'lg', onClick, selected, disabled, label}
 */
export function card(code, opts = {}) {
  const deck = opts.deck || 'fr';
  const hidden = !code || code === '??';
  const cls = 'pcard ' + (opts.size || 'md') + (opts.selected ? ' sel' : '') + (opts.onClick ? ' click' : '')
    + (opts.disabled ? ' off' : '') + (opts.cls ? ' ' + opts.cls : '');
  const face = hidden
    ? h('img', { src: backSrc(deck), alt: '', draggable: 'false' })
    : code[0] === 'X'
      ? h('span', { class: 'joker' }, h('span', null, '🃏'), h('small', null, 'JOLLY'))
      : h('img', { src: `img/cards/${deck}/${code}.webp`, alt: '', draggable: 'false' });
  const label = opts.label || (hidden ? 'card' : cardName(code, deck));
  if (opts.onClick) {
    return h('button', { type: 'button', class: cls, 'aria-label': label, 'aria-pressed': opts.selected ? 'true' : null,
      disabled: opts.disabled || null, onclick: opts.onClick, 'data-card': code || '' }, face);
  }
  return h('span', { class: cls, role: 'img', 'aria-label': label, 'data-card': code || '' }, face);
}

/** A face-down pile with a count badge. */
export function pile(deck, count, label) {
  return h('span', { class: 'pile', title: label || '' }, card('??', { deck, size: 'sm' }),
    count != null ? h('span', { class: 'pile-n' }, String(count)) : null);
}
