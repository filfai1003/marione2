// Small helpers: safe DOM builder (never innerHTML), locale-aware formatting, file checks.
import { t, locale } from './i18n.js';

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

/** Replaces the children of `el`, skipping null/false (unlike replaceChildren, which prints "null"). */
export function fill(el, ...kids) { el.replaceChildren(); return append(el, kids); }

/** Ricostruisce il contenuto di `el` solo se la chiave cambia (evita flicker e perdita di focus). */
export function region(el, key, build) {
  if (el._k === key) return;
  el._k = key;
  el.replaceChildren();
  append(el, [build()]);
}

export function fmt(n) {
  const v = Math.round(Number(n) || 0);
  return new Intl.NumberFormat(locale()).format(v).replace('-', '−');
}

export function abbrev(n) {
  const v = Number(n) || 0;
  if (Math.abs(v) <= 99999) return fmt(v);
  return new Intl.NumberFormat(locale(), { notation: 'compact', maximumFractionDigits: 1 }).format(v);
}

export function ago(iso) {
  const ms = new Date(iso).getTime();
  if (!ms) return '';
  const s = (ms - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' });
  const a = Math.abs(s);
  if (a < 45) return rtf.format(0, 'second');
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute');
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour');
  if (a < 14 * 86400) return rtf.format(Math.round(s / 86400), 'day');
  return new Date(ms).toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: a > 300 * 86400 ? 'numeric' : undefined });
}

export function mmss(sec) {
  const s = Math.max(0, Math.ceil(sec));
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  const p = (x) => String(x).padStart(2, '0');
  return hh ? `${hh}:${p(mm)}:${p(ss)}` : `${p(mm)}:${p(ss)}`;
}

export const fmtDur = (ms) => (ms ? new Intl.NumberFormat(locale(), { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(ms / 1000) + ' s' : '—');
export const fmtKB = (b) => Math.max(1, Math.round(b / 1024)) + ' KB';
export const fileBase = (n) => n.replace(/\.[^.]+$/, '').slice(0, 40);

export function firstGrapheme(s) {
  s = (s || '').trim();
  if (!s) return '';
  if (window.Intl && Intl.Segmenter) {
    const it = new Intl.Segmenter(locale(), { granularity: 'grapheme' }).segment(s)[Symbol.iterator]().next();
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
  if (!okType) return t('file.notAudio');
  if (file.size > MAX_BYTES) return t('file.tooBig');
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
