// Piccole utilità: DOM builder sicuro (mai innerHTML), formattazione it-IT, validazione file.

const PROPS = new Set(['value', 'checked', 'disabled', 'selected', 'hidden']);

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style' && typeof v === 'object') {
        for (const [sk, sv] of Object.entries(v)) {
          if (sk.startsWith('--')) el.style.setProperty(sk, sv);
          else el.style[sk] = sv;
        }
      } else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (PROPS.has(k)) el[k] = v;
      else el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  append(el, kids);
  return el;
}

export function append(el, kids) {
  for (const k of kids) {
    if (k == null || k === false) continue;
    if (Array.isArray(k)) append(el, k);
    else el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

/** Ricostruisce il contenuto di `el` solo se la chiave cambia (evita flicker e perdita di focus). */
export function region(el, key, build) {
  if (el._k === key) return;
  el._k = key;
  el.replaceChildren();
  append(el, [build()]);
}

export function fmt(n) {
  const v = Math.round(Number(n) || 0);
  const s = String(Math.abs(v)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return (v < 0 ? '−' : '') + s;
}

export function abbrev(n) {
  const v = Number(n) || 0;
  if (Math.abs(v) <= 99999) return fmt(v);
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1).replace('.', ',').replace(',0', '') + 'M';
  return Math.round(v / 1000) + 'k';
}

export function ago(iso) {
  const t = new Date(iso).getTime();
  if (!t) return '';
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 45) return 'adesso';
  if (s < 3600) return Math.round(s / 60) + ' min fa';
  if (s < 86400) { const o = Math.round(s / 3600); return o === 1 ? '1 ora fa' : o + ' ore fa'; }
  const d = Math.floor(s / 86400);
  if (d === 1) return 'ieri';
  if (d < 14) return d + ' giorni fa';
  return new Date(t).toLocaleDateString('it-IT', { day: 'numeric', month: 'short' });
}

export function mmss(sec) {
  const s = Math.max(0, Math.ceil(sec));
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  const p = (x) => String(x).padStart(2, '0');
  return hh ? `${hh}:${p(mm)}:${p(ss)}` : `${p(mm)}:${p(ss)}`;
}

export const fmtDur = (ms) => (ms / 1000).toFixed(1).replace('.', ',') + ' s';
export const fmtKB = (b) => Math.max(1, Math.round(b / 1024)) + ' KB';
export const fileBase = (n) => n.replace(/\.[^.]+$/, '').slice(0, 40);

export function firstGrapheme(s) {
  s = (s || '').trim();
  if (!s) return '';
  if (window.Intl && Intl.Segmenter) {
    const it = new Intl.Segmenter('it', { granularity: 'grapheme' }).segment(s)[Symbol.iterator]().next();
    return it.value ? it.value.segment : '';
  }
  return Array.from(s)[0];
}

export function debounce(fn, ms) {
  let t;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  d.cancel = () => clearTimeout(t);
  return d;
}

export const MAX_BYTES = 8 * 1024 * 1024;
export function checkAudio(file) {
  const okType = file.type ? file.type.startsWith('audio/') : /\.(mp3|wav|ogg)$/i.test(file.name);
  if (!okType) return 'Serve un file audio (mp3, wav o ogg).';
  if (file.size > MAX_BYTES) return 'File troppo grande: massimo 8 MB.';
  return null;
}

const HEX = /^#[0-9a-f]{3,8}$/i;
export const safeColor = (c) => (HEX.test(c || '') ? c : '#95A5A6');

const AV = ['#d5321f', '#2f8f36', '#d29a0a', '#2c6fa8', '#8a5e34', '#9B59B6', '#1ABC9C'];
export function avatar(u, size = 36) {
  const name = (u && u.name) || '?';
  const letter = (Array.from(name.trim())[0] || '?').toUpperCase();
  let hash = 0;
  for (const c of name) hash = (hash * 31 + c.codePointAt(0)) >>> 0;
  const el = h('span', { class: 'avatar', 'aria-hidden': 'true',
    style: { width: size + 'px', height: size + 'px', fontSize: Math.round(size * 0.46) + 'px', '--bg': AV[hash % AV.length] } }, letter);
  if (u && u.avatar) {
    const img = h('img', { src: u.avatar, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
    img.addEventListener('error', () => img.remove());
    el.append(img);
  }
  return el;
}
