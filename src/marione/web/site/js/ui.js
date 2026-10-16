// Shared components: cards, badges, history, modal, tabs, pager, collapsible sections, uploads.
import { h, fmt, ago, safeColor, fileBase, firstGrapheme, debounce } from './util.js';
import { t } from './i18n.js';

export const card = (cls, ...kids) => h('section', { class: 'card ' + (cls || '') }, ...kids);

export const pageHead = (title, sub, extra) =>
  h('div', { class: 'page-head' }, h('div', null, h('h1', null, title), sub ? h('p', null, sub) : null), extra || null);

export const cardTitle = (emoji, text, extra) =>
  h('div', { class: 'card-title' }, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, emoji), h('h2', null, text), extra);

export const notice = (emoji, title, text, action) =>
  card('notice', h('div', { class: 'notice-emoji mar-anim-bob', 'aria-hidden': 'true' }, emoji), h('h2', null, title), h('p', null, text), action);

export const empty = (emoji, text) => h('div', { class: 'empty-state' }, h('span', { 'aria-hidden': 'true' }, emoji), h('p', null, text));

export function tierBadge(tier) {
  return h('span', { class: 'tier', style: { '--c': safeColor(tier.color) }, title: tier.name },
    h('span', { class: 'tier-emoji' }, tier.emoji), h('span', { class: 'tier-name' }, tier.name));
}

export const field = (label, control, hint, error) =>
  h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), control,
    error || null, hint ? h('span', { class: 'hint' }, hint) : null);

export function btn(label, cls, props) {
  return h('button', { type: 'button', class: 'btn ' + (cls || ''), ...props }, label);
}

export function fillSelect(sel, members, placeholder) {
  const key = JSON.stringify([placeholder, members.map((m) => [m.id, m.name])]);
  if (sel._k === key) return;
  sel._k = key;
  const prev = sel.value;
  sel.replaceChildren(h('option', { value: '' }, placeholder));
  for (const m of members) sel.append(h('option', { value: m.id }, m.name));
  if (members.some((m) => m.id === prev)) sel.value = prev;
}

export function historyList(items, emptyText) {
  if (!items.length) return empty('📭', emptyText || t('history.empty'));
  return h('ul', { class: 'hist' }, items.map((r) => {
    const neg = r.delta < 0;
    return h('li', null,
      h('span', { class: 'hist-ico ' + (neg ? 'neg' : 'pos'), 'aria-hidden': 'true' }, neg ? '↘' : '↗'),
      h('span', { class: 'hist-main' }, h('strong', null, r.label), h('small', null, ago(r.at))),
      h('span', { class: 'delta ' + (neg ? 'neg' : 'pos') }, (neg ? '−' : '+') + fmt(Math.abs(r.delta)), ' 🪙'));
  }));
}

export function progress(pct, label, cls = '') {
  const p = Math.max(0, Math.min(100, pct));
  return h('div', { class: 'progress ' + cls, role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100',
    'aria-valuenow': String(Math.round(p)), 'aria-label': label || '' },
  h('div', { class: 'progress-fill', style: { width: p + '%' } }));
}

/** Inline field error under an input (role=alert so screen readers hear it). */
export function fieldError() {
  const el = h('span', { class: 'field-err', role: 'alert', hidden: true });
  return {
    el,
    show(msg) { el.textContent = msg; el.hidden = !msg; },
  };
}

// ---- tabs (ARIA tablist, arrow keys move between tabs) ----
export function tabs(items, active, onChange) {
  const list = h('div', { class: 'tabs', role: 'tablist' });
  const buttons = items.map(([key, emoji, label]) => {
    const b = h('button', { type: 'button', class: 'tab', role: 'tab', id: 'tab-' + key, 'data-k': key,
      'aria-selected': String(key === active), tabindex: key === active ? '0' : '-1',
      onclick: () => select(key, true) }, h('span', { 'aria-hidden': 'true' }, emoji), h('span', null, label));
    return b;
  });
  list.append(...buttons);
  list.addEventListener('keydown', (e) => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) return;
    const i = buttons.findIndex((b) => b.getAttribute('aria-selected') === 'true');
    const n = buttons.length;
    const j = e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + n) % n;
    e.preventDefault();
    select(buttons[j].dataset.k, true);
    buttons[j].focus();
  });
  function select(key, user) {
    buttons.forEach((b) => {
      const on = b.dataset.k === key;
      b.setAttribute('aria-selected', String(on));
      b.tabIndex = on ? 0 : -1;
    });
    if (user) onChange(key);
  }
  return { el: list, select: (k) => select(k, false) };
}

// ---- pager: "‹ Previous · Page X of Y · Next ›" ----
export function pager(total, offset, limit, onPage) {
  const pages = Math.max(1, Math.ceil(total / limit));
  const page = Math.floor(offset / limit) + 1;
  if (pages <= 1) return null;
  const go = (p) => onPage((p - 1) * limit);
  return h('nav', { class: 'pager', 'aria-label': t('pager.label') },
    btn('‹ ' + t('pager.prev'), 'ghost sm', { disabled: page <= 1, onclick: () => go(page - 1) }),
    h('span', { class: 'pager-info', 'aria-live': 'polite' }, t('pager.info', { page, pages })),
    btn(t('pager.next') + ' ›', 'ghost sm', { disabled: page >= pages, onclick: () => go(page + 1) }));
}

// ---- search box with a clear button, debounced ----
export function searchBox(placeholder, onSearch, ms = 250) {
  const input = h('input', { type: 'search', placeholder, 'aria-label': placeholder, autocomplete: 'off', enterkeyhint: 'search' });
  const fire = debounce(() => onSearch(input.value.trim()), ms);
  input.addEventListener('input', fire);
  input.addEventListener('keydown', (e) => { if (e.key === 'Escape' && input.value) { input.value = ''; fire.cancel(); onSearch(''); } });
  const wrap = h('div', { class: 'search' }, h('span', { class: 'search-ico', 'aria-hidden': 'true' }, '🔎'), input);
  return { el: wrap, input, cancel: fire.cancel };
}

// ---- collapsible section (native <details>: keyboard and screen reader support for free) ----
export function collapsible(emoji, title, sub, content, open = false) {
  const d = h('details', { class: 'card fold', open: open || null },
    h('summary', null, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, emoji),
      h('span', { class: 'fold-title' }, h('h2', null, title), sub ? h('small', null, sub) : null),
      h('span', { class: 'fold-chev', 'aria-hidden': 'true' }, '▾')),
    h('div', { class: 'fold-body' }, content));
  return d;
}

// ---- filter chips (radio group) ----
export function chipGroup(items, active, onChange, label) {
  const g = h('div', { class: 'chips filter', role: 'radiogroup', 'aria-label': label });
  const set = (k) => g.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-checked', String(c.dataset.k === k)));
  for (const [k, text] of items) {
    g.append(h('button', { type: 'button', class: 'chip', role: 'radio', 'data-k': k, 'aria-checked': String(k === active),
      onclick: () => { set(k); onChange(k); } }, text));
  }
  return g;
}

// ---- modal (native dialog: focus trap + Esc for free) ----
export function modal(title, content, actions, cls = '') {
  const dlg = h('dialog', { class: 'modal ' + cls, 'aria-label': title });
  const close = () => dlg.close();
  dlg.append(
    h('div', { class: 'modal-head' }, h('h2', null, title),
      h('button', { type: 'button', class: 'icon-btn', 'aria-label': t('common.close'), onclick: close }, '✕')),
    h('div', { class: 'modal-body' }, content),
    actions ? h('div', { class: 'modal-foot' }, actions(close)) : null);
  dlg.addEventListener('click', (e) => { if (e.target === dlg) close(); });
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  return { dlg, close };
}

export function confirmDialog(title, text, okLabel, onOk) {
  return modal(title, h('p', null, text), (close) => [
    btn(t('common.cancel'), 'ghost', { onclick: close }),
    btn(okLabel, 'danger', { onclick: async (e) => { await onOk(e.currentTarget); close(); } }),
  ]);
}

export const EMOJI = ['🔊', '🎺', '👏', '🥁', '🎸', '🎹', '😂', '🤣', '😱', '😎', '🔥', '💥',
  '🎉', '🍕', '🍝', '🤌', '👀', '💩', '🐔', '🐶', '🚨', '📣', '🎵', '🤡'];

/**
 * "Name (+ emoji)" modal to add or rename a sound.
 * opts: {title, file?, name, emoji?, withEmoji, okLabel, onSubmit({name, emoji}, btn)}
 */
export function nameModal(opts) {
  const name = h('input', { type: 'text', maxlength: '40', required: true, value: opts.name || '', autocomplete: 'off' });
  const emoji = h('input', { type: 'text', maxlength: '8', class: 'emoji-in', value: opts.emoji || '', placeholder: '🔊', 'aria-label': t('sound.emoji') });
  const err = fieldError();
  const picker = h('div', { class: 'emoji-grid', role: 'group', 'aria-label': t('sound.pickEmoji') }, EMOJI.map((e) =>
    h('button', { type: 'button', class: 'emoji-pick', 'aria-label': e, onclick: () => { emoji.value = e; } }, e)));
  const body = h('form', { class: 'stack', onsubmit: (e) => { e.preventDefault(); ok.click(); } },
    opts.file ? h('p', { class: 'file-chip' }, '🎵 ', opts.file.name, h('small', null, ' · ' + (opts.file.size / 1024 / 1024).toFixed(2) + ' MB')) : null,
    field(t('sound.name'), name, null, err.el),
    opts.withEmoji ? h('div', { class: 'field' }, h('span', { class: 'field-label' }, t('sound.emoji')), emoji, picker) : null);
  let ok;
  const { dlg } = modal(opts.title, body, (close) => {
    ok = btn(opts.okLabel || t('common.save'), 'primary', { onclick: async (e) => {
      const n = name.value.trim();
      if (!n) { err.show(t('sound.nameRequired')); name.focus(); return; }
      err.show('');
      const b = e.currentTarget;
      if (b.disabled) return;
      b.disabled = true; b.classList.add('busy');
      try { if (await opts.onSubmit({ name: n, emoji: firstGrapheme(emoji.value) }, b) !== false) close(); }
      finally { b.disabled = false; b.classList.remove('busy'); }
    } });
    return [btn(t('common.cancel'), 'ghost', { onclick: close }), ok];
  });
  name.focus(); name.select();
  return dlg;
}

export function pickFile(cb) {
  const inp = h('input', { type: 'file', accept: 'audio/*,.mp3,.wav,.ogg' });
  inp.addEventListener('change', () => { if (inp.files[0]) cb(inp.files[0]); });
  inp.click();
}

/** A single browser audio preview at a time, shared by every page. */
let previewAudio = null, previewKey = null;
const previewSubs = new Set();
export const preview = {
  key: () => previewKey,
  toggle(key, url, onError) {
    const wasOn = previewKey === key;
    preview.stop();
    if (wasOn) return;
    previewAudio = new Audio(url);
    previewKey = key;
    previewAudio.addEventListener('ended', () => preview.stop());
    previewAudio.addEventListener('error', () => { preview.stop(); if (onError) onError(); });
    previewAudio.play().catch(() => {});
    previewSubs.forEach((f) => f());
  },
  stop() {
    if (previewAudio) previewAudio.pause();
    previewAudio = null; previewKey = null;
    previewSubs.forEach((f) => f());
  },
  subscribe(f) { previewSubs.add(f); return () => previewSubs.delete(f); },
};

export { fileBase };

// ---- popover menu anchored to a button (Esc, outside click and picking an item close it) ----
let openMenu = null;
export function closeMenu() { if (openMenu) { openMenu(); openMenu = null; } }
/**
 * items: array of [emoji, label, onClick, cls?] or a DOM node (a custom row); null entries are skipped.
 */
export function popover(anchor, items, cls = '') {
  if (anchor.getAttribute('aria-expanded') === 'true') { closeMenu(); return; }
  closeMenu();
  const box = h('div', { class: 'menu ' + cls, role: 'menu' }, items.filter(Boolean).map((it) => {
    if (it instanceof Node) return it;
    const [emoji, label, fn, c] = it;
    return h('button', { type: 'button', role: 'menuitem', class: 'menu-item ' + (c || ''),
      onclick: () => { closeMenu(); fn(); } }, h('span', { 'aria-hidden': 'true' }, emoji), h('span', null, label));
  }));
  document.body.append(box);
  const r = anchor.getBoundingClientRect();
  const w = box.offsetWidth, hgt = box.offsetHeight;
  const left = Math.min(Math.max(8, r.right - w), window.innerWidth - w - 8);
  const below = r.bottom + 6 + hgt < window.innerHeight;
  box.style.left = left + 'px';
  box.style.top = (below ? r.bottom + 6 : Math.max(8, r.top - hgt - 6)) + 'px';
  anchor.setAttribute('aria-expanded', 'true');
  const first = box.querySelector('button, select, a');
  if (first) first.focus();
  const onDoc = (e) => { if (!box.contains(e.target) && !anchor.contains(e.target)) closeMenu(); };
  const onKey = (e) => {
    if (e.key === 'Escape') { closeMenu(); anchor.focus(); }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const all = [...box.querySelectorAll('.menu-item')];
      const i = all.indexOf(document.activeElement);
      const j = (i + (e.key === 'ArrowDown' ? 1 : -1) + all.length) % all.length;
      if (all[j]) { e.preventDefault(); all[j].focus(); }
    }
  };
  setTimeout(() => document.addEventListener('pointerdown', onDoc), 0);
  document.addEventListener('keydown', onKey);
  window.addEventListener('hashchange', closeMenu, { once: true });
  openMenu = () => {
    document.removeEventListener('pointerdown', onDoc);
    document.removeEventListener('keydown', onKey);
    anchor.setAttribute('aria-expanded', 'false');
    box.remove();
  };
}

/** A square cover image with an emoji fallback. */
export function cover(src, size = 56, emoji = '🎵', cls = '') {
  const box = h('span', { class: 'cover ' + cls, style: { width: size + 'px', height: size + 'px' }, 'aria-hidden': 'true' }, emoji);
  if (src) {
    const img = h('img', { src, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
    img.addEventListener('error', () => img.remove());
    box.append(img);
  }
  return box;
}
