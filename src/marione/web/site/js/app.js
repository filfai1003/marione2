// Bootstrap: session, shell (header + navigation), hash router, polling, global drag & drop.
import { h, fmt, avatar } from './util.js';
import { store, set, subscribe } from './store.js';
import { api, post, hooks } from './api.js';
import { refreshState, startPolling, stopPolling, handleError } from './data.js';
import { toast } from './toast.js';
import { t, getLang, setLang, LANGS, LANG_NAMES, initialLang } from './i18n.js';
import { preview, popover, closeMenu } from './ui.js';
import { setMusicEnabled } from './player.js';
import { playerBar } from './playerbar.js';
import * as home from './pages/home.js';
import * as economy from './pages/economy.js';
import * as soundboard from './pages/soundboard.js';
import * as music from './pages/music.js';
import * as entrances from './pages/entrances.js';
import * as brain from './pages/brain.js';
import * as settings from './pages/settings.js';
import * as admin from './pages/admin.js';
import * as games from './pages/games.js';
import { icon } from './art.js';

// Order = sidebar order. The five everyday pages are also the phone's bottom tabs (each tab opens a
// page, never a menu); on phones admins reach the Admin hub from the account menu.
const PAGES = {
  home: { icon: 'home', mod: home },
  economy: { icon: 'economy', mod: economy },
  games: { icon: 'games', mod: games },
  soundboard: { icon: 'soundboard', mod: soundboard },
  music: { icon: 'music', mod: music },
  admin: { icon: 'admin', mod: admin, admin: true, hub: true },
  entrances: { icon: 'entrances', mod: entrances, admin: true },
  brain: { icon: 'brain', mod: brain, admin: true },
  settings: { icon: 'settings', mod: settings, admin: true },
};
const root = document.getElementById('root');
let shell = null, current = null, currentKey = null;

// ---------- theme ----------
function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('marione-theme', next); } catch { /* storage blocked */ }
}

// ---------- language ----------
function langPicker() {
  const sel = h('select', { class: 'lang-pick', 'aria-label': t('lang.label') },
    LANGS.map((l) => h('option', { value: l, selected: l === getLang() }, LANG_NAMES[l])));
  sel.addEventListener('change', () => { closeMenu(); changeLang(sel.value); });
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

// ---------- account menu: who you are, language, theme, log out ----------
function openAccount(anchor) {
  const me = store.me;
  const dark = document.documentElement.dataset.theme === 'dark';
  popover(anchor, [
    h('div', { class: 'menu-head' }, avatar(me, 40), h('span', null, h('strong', null, me.name),
      me.isAdmin ? h('small', null, t('nav.admin')) : null)),
    h('label', { class: 'menu-row' }, h('span', null, '🌍 ' + t('lang.label')), langPicker()),
    me.isAdmin ? ['🛠️', t('nav.adminTools'), () => { location.hash = '#/admin'; }, 'mobile-only-item'] : null,
    ['🎨', dark ? t('theme.light') : t('theme.dark'), toggleTheme],
    ['🚪', t('nav.logout'), () => { location.href = '/auth/logout'; }, 'danger'],
  ], 'account-menu');
}

// ---------- simple screens ----------
function screen(emoji, title, text, action) {
  if (shell && shell.bar) shell.bar.destroy();
  document.body.classList.remove('has-player');
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

function navLink(k, p, cls = 'nav-item') {
  return h('a', { class: cls, href: '#/' + k, 'data-k': k },
    h('span', { class: 'nav-emoji' }, icon(p.icon, 30)), h('span', { class: 'nav-label' }, label(k)));
}

function buildShell() {
  if (shell && shell.bar) shell.bar.destroy();
  const entries = Object.entries(PAGES).filter(([, p]) => visible(p));
  // Sidebar (wide screens): everyday pages, then the admin pages in their own group.
  const nav = h('nav', { class: 'nav', 'aria-label': t('nav.sections') },
    h('a', { class: 'brand', href: '#/home', 'aria-label': t('nav.homeAria') },
      h('span', { class: 'logo', 'aria-hidden': 'true' }, '🍝'), h('span', { class: 'wordmark' }, 'Marione')),
    entries.filter(([, p]) => !p.admin).map(([k, p]) => navLink(k, p)),
    store.me.isAdmin ? h('div', { class: 'nav-group' }, h('span', { class: 'nav-group-label' }, t('nav.admin')),
      entries.filter(([, p]) => p.admin && !p.hub).map(([k, p]) => navLink(k, p))) : null,
    h('div', { class: 'nav-foot' }, h('span', { class: 'script' }, t('nav.bonappetit'))));
  // Bottom tabs (phones).
  const tabbar = h('nav', { class: 'tabbar', 'aria-label': t('nav.sections') },
    entries.filter(([, p]) => !p.admin).map(([k, p]) => navLink(k, p, 'tab-item')));
  const voice = h('span', { class: 'pill voice' }), coin = h('span', { class: 'coin-val' });
  const offline = h('span', { class: 'offline', title: t('common.offline'), role: 'status', hidden: true });
  const av = h('span', { class: 'me-av' });
  const account = h('button', { type: 'button', class: 'account-btn', 'aria-haspopup': 'menu', 'aria-expanded': 'false',
    'aria-label': t('nav.account'), onclick: (e) => openAccount(e.currentTarget) }, av, offline, h('span', { class: 'chev', 'aria-hidden': 'true' }, '▾'));
  const header = h('header', { class: 'topbar' },
    h('a', { class: 'brand mobile-only', href: '#/home', 'aria-label': t('nav.homeAria') }, h('span', { class: 'logo', 'aria-hidden': 'true' }, '🍝')),
    voice, h('span', { class: 'spacer' }),
    h('a', { class: 'pill coin', href: '#/economy/history', title: t('header.coins') }, h('span', { 'aria-hidden': 'true' }, '🪙'), coin),
    account);
  const view = h('main', { class: 'view', id: 'view', tabindex: '-1' });
  const bar = playerBar();
  const veil = h('div', { class: 'dropveil', hidden: true }, h('div', null, h('span', null, '🎵'), h('strong', null, t('drop.release'))));
  root.replaceChildren(h('a', { class: 'skip', href: '#view' }, t('common.skip')),
    h('div', { class: 'app' }, nav, header, view), bar.el, tabbar, veil);
  shell = { nav, tabbar, voice, coin, av, offline, view, veil, bar, avKey: '' };
  document.documentElement.lang = getLang();
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
  if (shell.avKey !== k) { shell.avKey = k; shell.av.replaceChildren(avatar(me, 36)); }
  if (store.state) setMusicEnabled(!!store.state.modules.music);
}

// ---------- router: #/page[/sub] ----------
function route() {
  if (store.view !== 'app' || !shell) return;
  const [, key0, sub] = location.hash.match(/^#\/([a-z]+)(?:\/([a-z0-9-]+))?/) || [];
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
  // Admin pages are reached from the Admin hub on phones: give them a way back.
  if (PAGES[key].admin && !PAGES[key].hub) {
    holder.append(h('a', { class: 'crumb mobile-only', href: '#/admin' }, '‹ ' + t('nav.admin')));
  }
  current = PAGES[key].mod.mount(holder, sub);
  const tabKey = key;
  shell.nav.querySelectorAll('[data-k]').forEach((a) => {
    if (a.dataset.k === key) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  shell.tabbar.querySelectorAll('[data-k]').forEach((a) => {
    if (a.dataset.k === tabKey) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  document.title = label(key) + ' · Marione';
  closeMenu();
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
