// Bootstrap: session, shell (header + navigation), hash router, polling, global drag & drop.
import { h, fmt, avatar } from './util.js';
import { store, set, subscribe } from './store.js';
import { api, post, hooks } from './api.js';
import { refreshState, startPolling, stopPolling, handleError } from './data.js';
import { toast } from './toast.js';
import { t, getLang, setLang, LANGS, LANG_NAMES, initialLang } from './i18n.js';
import { modal, preview } from './ui.js';
import * as home from './pages/home.js';
import * as economy from './pages/economy.js';
import * as soundboard from './pages/soundboard.js';
import * as music from './pages/music.js';
import * as entrances from './pages/entrances.js';
import * as brain from './pages/brain.js';
import * as settings from './pages/settings.js';

// Order = sidebar order. `main` pages are on the mobile bottom bar; the rest go under "More".
const PAGES = {
  home: { emoji: '🛋️', mod: home, main: true },
  economy: { emoji: '💰', mod: economy, main: true },
  soundboard: { emoji: '🔊', mod: soundboard, main: true },
  music: { emoji: '🎵', mod: music, main: true },
  entrances: { emoji: '🎺', mod: entrances, admin: true },
  brain: { emoji: '🧠', mod: brain, admin: true },
  settings: { emoji: '⚙️', mod: settings, admin: true },
};
const root = document.getElementById('root');
let shell = null, current = null, currentKey = null;

// ---------- theme ----------
function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('marione-theme', next); } catch { /* storage blocked */ }
  if (shell) syncTheme();
}
const syncTheme = () => {
  const dark = document.documentElement.dataset.theme === 'dark';
  shell.theme.textContent = dark ? '☀️' : '🌙';
  shell.theme.setAttribute('aria-label', dark ? t('theme.light') : t('theme.dark'));
};

// ---------- language ----------
function langPicker() {
  const sel = h('select', { class: 'lang-pick', 'aria-label': t('lang.label') },
    LANGS.map((l) => h('option', { value: l, selected: l === getLang() }, l.toUpperCase())));
  sel.addEventListener('change', () => changeLang(sel.value));
  return sel;
}
async function changeLang(code) {
  setLang(code);
  if (store.view === 'app') {
    try { await post('/api/settings/language', { lang: code }); } catch (e) { handleError(e); }
    rebuild();
    await refreshState();
    toast(t('lang.changed', { name: LANG_NAMES[code] }));
  } else if (store.view === 'login') showLogin(store.loginInfo);
}

// ---------- simple screens ----------
function screen(emoji, title, text, action) {
  shell = null; current = null; currentKey = null;
  root.replaceChildren(h('main', { class: 'center-screen' }, h('div', { class: 'card login mar-anim-pop' },
    h('div', { class: 'login-lang' }, langPicker()),
    h('div', { class: 'logo big mar-anim-bob', 'aria-hidden': 'true' }, emoji),
    h('p', { class: 'script' }, 'Marione'), h('h1', null, title), h('p', null, text), action)));
}
const showLogin = (me) => me && me.configured === false
  ? screen('🔧', t('login.notConfiguredTitle'), t('login.notConfiguredText'))
  : screen('🍝', t('login.title'), t('login.text'), h('a', { class: 'btn primary lg', href: '/auth/login' }, t('login.button')));
const showNotInGuild = () => screen('🚪', t('guild.title'), t('guild.text'),
  h('a', { class: 'btn ghost', href: '/auth/logout' }, t('nav.logout')));

// ---------- shell ----------
const visible = (p) => !p.admin || (store.me && store.me.isAdmin);
const label = (k) => t('nav.' + k);

function navLink(k, p) {
  return h('a', { class: 'nav-item', href: '#/' + k, 'data-k': k },
    h('span', { class: 'nav-emoji', 'aria-hidden': 'true' }, p.emoji), h('span', { class: 'nav-label' }, label(k)));
}

function openMore() {
  const items = Object.entries(PAGES).filter(([, p]) => !p.main && visible(p));
  const { close } = modal(t('nav.more'), h('div', { class: 'more-list' },
    items.map(([k, p]) => h('a', { class: 'more-item', href: '#/' + k, onclick: () => close() },
      h('span', { 'aria-hidden': 'true' }, p.emoji), h('span', null, label(k)))),
    h('div', { class: 'more-row' }, h('span', null, '🌍 ' + t('lang.label')), langPicker()),
    h('a', { class: 'more-item', href: '/auth/logout' }, h('span', { 'aria-hidden': 'true' }, '🚪'), h('span', null, t('nav.logout')))), null, 'sheet');
}

function buildShell() {
  const entries = Object.entries(PAGES).filter(([, p]) => visible(p));
  const mainLinks = entries.filter(([, p]) => !p.admin).map(([k, p]) => navLink(k, p));
  const adminLinks = entries.filter(([, p]) => p.admin).map(([k, p]) => navLink(k, p));
  const moreBtn = h('button', { type: 'button', class: 'nav-item more-btn', onclick: openMore, 'aria-haspopup': 'dialog' },
    h('span', { class: 'nav-emoji', 'aria-hidden': 'true' }, '☰'), h('span', { class: 'nav-label' }, t('nav.more')));
  const nav = h('nav', { class: 'nav', 'aria-label': t('nav.sections') },
    mainLinks,
    adminLinks.length ? h('div', { class: 'nav-group' }, h('span', { class: 'nav-group-label' }, t('nav.admin')), adminLinks) : null,
    moreBtn,
    h('div', { class: 'nav-foot' }, h('span', { class: 'script' }, t('nav.bonappetit')), h('a', { class: 'link', href: '/auth/logout' }, t('nav.logout'))));
  const voice = h('span', { class: 'pill voice' }), coin = h('span', { class: 'coin-val' });
  const offline = h('span', { class: 'offline', title: t('common.offline'), role: 'status', hidden: true });
  const theme = h('button', { type: 'button', class: 'icon-btn round', onclick: toggleTheme });
  const av = h('span', { class: 'me-av' });
  const header = h('header', { class: 'topbar' },
    h('a', { class: 'brand', href: '#/home', 'aria-label': t('nav.homeAria') }, h('span', { class: 'logo', 'aria-hidden': 'true' }, '🍝'), h('span', { class: 'wordmark' }, 'Marione')),
    voice, h('span', { class: 'spacer' }),
    h('a', { class: 'pill coin', href: '#/economy/history', title: t('header.coins') }, h('span', { 'aria-hidden': 'true' }, '🪙'), coin),
    h('span', { class: 'hide-sm' }, langPicker()), theme, h('span', { class: 'me' }, av, offline));
  const view = h('main', { class: 'view', id: 'view', tabindex: '-1' });
  const veil = h('div', { class: 'dropveil', hidden: true }, h('div', null, h('span', null, '🎵'), h('strong', null, t('drop.release'))));
  root.replaceChildren(h('a', { class: 'skip', href: '#view' }, t('common.skip')), h('div', { class: 'app' }, header, nav, view), veil);
  shell = { nav, voice, coin, theme, av, offline, view, veil, avKey: '' };
  document.documentElement.lang = getLang();
  syncTheme();
}

function rebuild() {
  if (current && current.destroy) current.destroy();
  current = null; currentKey = null;
  buildShell();
  syncShell();
  route();
}

function syncShell() {
  if (!shell) return;
  const { me, balance } = store;
  const txt = fmt(balance);
  if (shell.coin.textContent !== txt) {
    const had = shell.coin.textContent !== '';
    shell.coin.textContent = txt;
    if (had) { shell.coin.classList.remove('bump'); void shell.coin.offsetWidth; shell.coin.classList.add('bump'); }
  }
  shell.voice.textContent = store.inVoice ? '🎧 ' + (store.voiceChannel || t('header.voice')) : '🔇 ' + t('header.notInVoice');
  shell.voice.classList.toggle('on', store.inVoice);
  shell.offline.hidden = store.online;
  const k = me.id + me.name + me.avatar;
  if (shell.avKey !== k) { shell.avKey = k; shell.av.replaceChildren(avatar(me, 40)); shell.av.title = me.name; }
}

// ---------- router: #/page[/sub] ----------
function route() {
  if (store.view !== 'app' || !shell) return;
  const [, key0, sub] = location.hash.match(/^#\/([a-z]+)(?:\/([a-z-]+))?/) || [];
  let key = key0;
  if (!PAGES[key] || !visible(PAGES[key])) {
    if (key !== 'home') location.replace('#/home');
    key = 'home';
  }
  if (key === currentKey) { if (current && current.route) current.route(sub); return; }
  if (current && current.destroy) current.destroy();
  preview.stop();
  currentKey = key;
  shell.view.replaceChildren();
  const holder = h('div', { class: 'page mar-anim-pop' });
  shell.view.append(holder);
  current = PAGES[key].mod.mount(holder, sub);
  shell.nav.querySelectorAll('.nav-item[data-k]').forEach((a) => {
    if (a.dataset.k === key) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  shell.nav.querySelector('.more-btn').classList.toggle('active', !PAGES[key].main);
  document.title = label(key) + ' · Marione';
  window.scrollTo(0, 0);
  if (store.state) current.update();
}

function onStore() {
  if (store.view === 'notguild') { stopPolling(); showNotInGuild(); return; }
  if (store.view !== 'app' || !shell) return;
  syncShell();
  route();
  if (current && store.state) current.update();
}

// ---------- global drag & drop ----------
function initDrop() {
  let depth = 0;
  const hasFiles = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');
  const veil = (on) => { if (shell) shell.veil.hidden = !on; };
  window.addEventListener('dragenter', (e) => { if (hasFiles(e) && shell) { e.preventDefault(); depth++; veil(true); } });
  window.addEventListener('dragover', (e) => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener('dragleave', (e) => { if (hasFiles(e) && --depth <= 0) { depth = 0; veil(false); } });
  window.addEventListener('drop', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault(); depth = 0; veil(false);
    const f = e.dataTransfer.files[0];
    if (!f || !shell || !store.state) return;
    if (currentKey === 'entrances' && current && current.drop) current.drop(f);
    else if (store.state.modules.soundboard) soundboard.openAdd(f);
    else toast(t('drop.paused'), 'err');
  });
}

// ---------- start ----------
async function boot() {
  setLang(initialLang());
  hooks.onUnauthorized = () => { if (store.view !== 'login') { stopPolling(); set({ view: 'login' }); showLogin({ configured: true }); } };
  let me;
  try { me = await api('/api/me'); } catch (e) {
    if (e.code !== 'unauthorized') {
      screen('📡', t('boot.unreachable'), e.message, h('button', { class: 'btn primary', type: 'button', onclick: () => location.reload() }, t('common.retry')));
      return;
    }
    me = { configured: true, loggedIn: false };
  }
  if (me.lang) setLang(me.lang);
  store.loginInfo = me;
  if (!me.loggedIn) { set({ view: 'login' }); showLogin(me); return; }
  if (!me.inGuild) { set({ view: 'notguild' }); return; }
  store.me = me;
  const s = await refreshState();
  if (!s) {
    if (store.view !== 'notguild' && store.view !== 'login') screen('📡', t('boot.noData'), t('boot.noDataText'), h('button', { class: 'btn primary', type: 'button', onclick: () => location.reload() }, t('common.retry')));
    return;
  }
  if (s.lang && s.lang !== getLang()) setLang(s.lang);
  store.view = 'app';
  buildShell();
  syncShell();
  route();
  startPolling();
  setInterval(() => { if (current && current.tick && !document.hidden) current.tick(); }, 1000);
}

subscribe(onStore);
window.addEventListener('hashchange', route);
initDrop();
boot();
