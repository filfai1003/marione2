// Componenti condivisi: card, badge, cronologia, modale, caricamento audio.
import { h, fmt, ago, safeColor, fileBase, firstGrapheme } from './util.js';

export const card = (cls, ...kids) => h('section', { class: 'card ' + (cls || '') }, ...kids);

export const pageHead = (title, sub) =>
  h('div', { class: 'page-head' }, h('h1', null, title), sub ? h('p', null, sub) : null);

export const cardTitle = (emoji, text, extra) =>
  h('div', { class: 'card-title' }, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, emoji), h('h2', null, text), extra);

export const notice = (emoji, title, text, action) =>
  card('notice', h('div', { class: 'notice-emoji mar-anim-bob', 'aria-hidden': 'true' }, emoji), h('h2', null, title), h('p', null, text), action);

export function tierBadge(t) {
  return h('span', { class: 'tier', style: { '--c': safeColor(t.color) }, title: t.name },
    h('span', { class: 'tier-emoji' }, t.emoji), h('span', { class: 'tier-name' }, t.name));
}

export const field = (label, control, hint) =>
  h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), control, hint ? h('span', { class: 'hint' }, hint) : null);

export function btn(label, cls, props) {
  return h('button', { type: 'button', class: 'btn ' + (cls || ''), ...props }, label);
}

export function fillSelect(sel, members, placeholder) {
  const key = JSON.stringify(members.map((m) => [m.id, m.name]));
  if (sel._k === key) return;
  sel._k = key;
  const prev = sel.value;
  sel.replaceChildren(h('option', { value: '' }, placeholder));
  for (const m of members) sel.append(h('option', { value: m.id }, m.name));
  if (members.some((m) => m.id === prev)) sel.value = prev;
}

export function historyList(items, empty = 'Ancora niente da raccontare.') {
  if (!items.length) return h('p', { class: 'muted empty' }, empty);
  return h('ul', { class: 'hist' }, items.map((r) => {
    const neg = r.delta < 0;
    const withTxt = r.with && !String(r.label).includes(r.with) ? ' · con ' + r.with : '';
    return h('li', null,
      h('span', { class: 'hist-ico ' + (neg ? 'neg' : 'pos'), 'aria-hidden': 'true' }, neg ? '↘' : '↗'),
      h('span', { class: 'hist-main' }, h('strong', null, r.label), h('small', null, ago(r.at) + withTxt)),
      h('span', { class: 'delta ' + (neg ? 'neg' : 'pos') }, (neg ? '−' : '+') + fmt(Math.abs(r.delta)), ' 🪙'));
  }));
}

export function progress(pct, label, cls = '') {
  const p = Math.max(0, Math.min(100, pct));
  return h('div', { class: 'progress ' + cls, role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100',
    'aria-valuenow': String(Math.round(p)), 'aria-label': label || 'Avanzamento' },
  h('div', { class: 'progress-fill', style: { width: p + '%' } }));
}

// ---- modale (dialog nativo: focus trap + Esc gratis) ----
export function modal(title, content, actions) {
  const dlg = h('dialog', { class: 'modal', 'aria-label': title });
  const close = () => dlg.close();
  dlg.append(
    h('div', { class: 'modal-head' }, h('h2', null, title),
      h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Chiudi', onclick: close }, '✕')),
    h('div', { class: 'modal-body' }, content),
    h('div', { class: 'modal-foot' }, actions(close)));
  dlg.addEventListener('click', (e) => { if (e.target === dlg) close(); });
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  return { dlg, close };
}

export function confirmDialog(title, text, okLabel, onOk) {
  return modal(title, h('p', null, text), (close) => [
    btn('Annulla', 'ghost', { onclick: close }),
    btn(okLabel, 'danger', { onclick: async (e) => { await onOk(e.currentTarget); close(); } }),
  ]);
}

export const EMOJI = ['🔊', '🎺', '👏', '🥁', '🎸', '🎹', '😂', '🤣', '😱', '😎', '🔥', '💥',
  '🎉', '🍕', '🍝', '🤌', '👀', '💩', '🐔', '🐶', '🚨', '📣', '🎵', '🤡'];

/**
 * Modale "nome (+ emoji)" per aggiungere o rinominare un suono.
 * opts: {title, file?, name, emoji?, withEmoji, okLabel, onSubmit({name, emoji}, btn)}
 */
export function nameModal(opts) {
  const name = h('input', { type: 'text', maxlength: '40', required: true, value: opts.name || '', autocomplete: 'off' });
  const emoji = h('input', { type: 'text', maxlength: '8', class: 'emoji-in', value: opts.emoji || '', placeholder: '🔊', 'aria-label': 'Emoji' });
  const picker = h('div', { class: 'emoji-grid', role: 'group', 'aria-label': 'Scegli un\'emoji' }, EMOJI.map((e) =>
    h('button', { type: 'button', class: 'emoji-pick', onclick: () => { emoji.value = e; picker.querySelectorAll('.on').forEach((x) => x.classList.remove('on')); } }, e)));
  const body = h('form', { class: 'stack', onsubmit: (e) => { e.preventDefault(); ok.click(); } },
    opts.file ? h('p', { class: 'file-chip' }, '🎵 ', opts.file.name, h('small', null, ' · ' + (opts.file.size / 1024 / 1024).toFixed(2).replace('.', ',') + ' MB')) : null,
    field('Nome', name),
    opts.withEmoji ? h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Emoji'), emoji, picker) : null);
  let ok;
  const { dlg } = modal(opts.title, body, (close) => {
    ok = btn(opts.okLabel || 'Salva', 'primary', { onclick: async (e) => {
      const n = name.value.trim();
      if (!n) { name.focus(); return; }
      const b = e.currentTarget;
      if (b.disabled) return;
      b.disabled = true; b.classList.add('busy');
      try { if (await opts.onSubmit({ name: n, emoji: firstGrapheme(emoji.value) }, b) !== false) close(); }
      finally { b.disabled = false; b.classList.remove('busy'); }
    } });
    return [btn('Annulla', 'ghost', { onclick: close }), ok];
  });
  name.focus(); name.select();
  return dlg;
}

export function pickFile(cb) {
  const inp = h('input', { type: 'file', accept: 'audio/*,.mp3,.wav,.ogg' });
  inp.addEventListener('change', () => { if (inp.files[0]) cb(inp.files[0]); });
  inp.click();
}

export { fileBase };
