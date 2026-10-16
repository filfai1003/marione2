// Bootstrap: sessione, shell (header + nav), router a hash, polling, drag&drop globale.
import { h, fmt, avatar, checkAudio } from './util.js';
import { store, set, subscribe } from './store.js';
import { api, hooks } from './api.js';
import { refreshState, startPolling, stopPolling } from './data.js';
import { toast } from './toast.js';
import * as home from './pages/home.js';
import * as economy from './pages/economy.js';
import * as soundboard from './pages/soundboard.js';
import * as entrances from './pages/entrances.js';
import * as settings from './pages/settings.js';

const PAGES = {
  divano: { label: 'Divano', emoji: '🛋️', mod: home },
  economia: { label: 'Economia', emoji: '💰', mod: economy },
  soundboard: { label: 'Soundboard', emoji: '🔊', mod: soundboard },
  entrate: { label: 'Entrate', emoji: '🎺', mod: entrances },
  impostazioni: { label: 'Impostazioni', emoji: '⚙️', mod: settings, admin: true },
};
const root = document.getElementById('root');
let shell = null, current = null, currentKey = null;

// ---------- tema ----------
function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('marione-theme', next); } catch { /* ignora */ }
  if (shell) syncTheme();
}
const syncTheme = () => {
  const dark = document.documentElement.dataset.theme === 'dark';
  shell.theme.textContent = dark ? '☀️' : '🌙';
  shell.theme.setAttribute('aria-label', dark ? 'Passa al tema chiaro' : 'Passa al tema scuro');
};

// ---------- schermate semplici ----------
function screen(emoji, title, text, action) {
  shell = null; current = null; currentKey = null;
  root.replaceChildren(h('main', { class: 'center-screen' }, h('div', { class: 'card login mar-anim-pop' },
    h('div', { class: 'logo big mar-anim-bob', 'aria-hidden': 'true' }, emoji),
    h('p', { class: 'script' }, 'Marione'), h('h1', null, title), h('p', null, text), action)));
}
const showLogin = (me) => me && me.configured === false
  ? screen('🔧', 'Login non configurato', 'Il pannello non è ancora collegato a Discord. Riprova più tardi.')
  : screen('🍝', 'Benvenuto da Marione', 'Entra con il tuo account Discord per vedere i tuoi Marioncelli, suonare la soundboard e scegliere la tua sigla d’entrata.',
    h('a', { class: 'btn primary lg', href: '/auth/login' }, 'Entra con Discord'));
const showNotInGuild = () => screen('🚪', 'Non sei nel server', 'Per usare Marione devi far parte del server Discord. Entra e poi ricarica la pagina.',
  h('a', { class: 'btn ghost', href: '/auth/logout' }, 'Esci'));

// ---------- shell ----------
function buildShell() {
  const nav = h('nav', { class: 'nav', 'aria-label': 'Sezioni' },
    Object.entries(PAGES).map(([k, p]) => h('a', { class: 'nav-item', href: '#/' + k, 'data-k': k, hidden: p.admin ? true : null },
      h('span', { class: 'nav-emoji', 'aria-hidden': 'true' }, p.emoji), h('span', { class: 'nav-label' }, p.label))),
    h('div', { class: 'nav-foot' }, h('span', { class: 'script' }, 'Buon appetito!'), h('a', { class: 'link', href: '/auth/logout' }, 'Esci')));
  const voice = h('span', { class: 'pill voice' }), coin = h('span', { class: 'coin-val' });
  const offline = h('span', { class: 'offline', title: 'Offline: mostro gli ultimi dati', role: 'status', hidden: true });
  const theme = h('button', { type: 'button', class: 'icon-btn round', onclick: toggleTheme });
  const av = h('span', { class: 'me-av' });
  const header = h('header', { class: 'topbar' },
    h('a', { class: 'brand', href: '#/divano', 'aria-label': 'Marione, vai al Divano' }, h('span', { class: 'logo', 'aria-hidden': 'true' }, '🍝'), h('span', { class: 'wordmark' }, 'Marione')),
    voice, h('span', { class: 'spacer' }),
    h('span', { class: 'pill coin', title: 'I tuoi Marioncelli' }, h('span', { 'aria-hidden': 'true' }, '🪙'), coin),
    theme, h('span', { class: 'me' }, av, offline));
  const view = h('main', { class: 'view', id: 'view', tabindex: '-1' });
  const veil = h('div', { class: 'dropveil', hidden: true }, h('div', null, h('span', null, '🎵'), h('strong', null, 'Rilascia il file per caricarlo')));
  root.replaceChildren(h('div', { class: 'app' }, header, nav, view), veil);
  shell = { nav, voice, coin, theme, av, offline, view, veil, avKey: '' };
  syncTheme();
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
  shell.voice.textContent = store.inVoice ? '🎧 #' + (store.voiceChannel || 'vocale') : '🔇 non sei in vocale';
  shell.voice.classList.toggle('on', store.inVoice);
  shell.offline.hidden = store.online;
  shell.nav.querySelector('[data-k=impostazioni]').hidden = !(me && me.isAdmin);
  const k = me.id + me.name + me.avatar;
  if (shell.avKey !== k) { shell.avKey = k; shell.av.replaceChildren(avatar(me, 40)); shell.av.title = me.name; }
}

// ---------- router ----------
function route() {
  if (store.view !== 'app' || !shell) return;
  let key = (location.hash.match(/^#\/([a-z]+)/) || [])[1];
  if (!PAGES[key] || (PAGES[key].admin && !store.me.isAdmin)) {
    if (key !== 'divano') { location.replace('#/divano'); }
    key = 'divano';
  }
  if (key === currentKey) return;
  if (current && current.destroy) current.destroy();
  currentKey = key;
  shell.view.replaceChildren();
  const holder = h('div', { class: 'page mar-anim-pop' });
  shell.view.append(holder);
  current = PAGES[key].mod.mount(holder);
  shell.nav.querySelectorAll('.nav-item').forEach((a) => {
    if (a.dataset.k === key) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  window.scrollTo(0, 0);
  if (store.state) current.update();
}

function onStore() {
  if (store.view === 'notguild' && shell !== undefined) { stopPolling(); showNotInGuild(); return; }
  if (store.view !== 'app' || !shell) return;
  syncShell();
  route();
  if (current && store.state) current.update();
}

// ---------- drag & drop globale ----------
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
    const m = store.state.modules;
    if (currentKey === 'entrate' && m.sound) entrances.openAdd(f);
    else if (m.soundboard) soundboard.openAdd(f);
    else if (m.sound) entrances.openAdd(f);
    else toast('Il caricamento di suoni è in pausa.', 'err');
  });
}

// ---------- avvio ----------
async function boot() {
  hooks.onUnauthorized = () => { if (store.view !== 'login') { stopPolling(); store.view = 'login'; showLogin({ configured: true }); } };
  let me;
  try { me = await api('/api/me'); } catch (e) {
    if (e.code !== 'unauthorized') {
      screen('📡', 'Non riesco a raggiungere Marione', e.message, h('button', { class: 'btn primary', type: 'button', onclick: () => location.reload() }, 'Riprova'));
      return;
    }
    me = { configured: true, loggedIn: false };
  }
  if (!me.loggedIn) { set({ view: 'login' }); showLogin(me); return; }
  if (!me.inGuild) { set({ view: 'notguild' }); return; }
  store.me = me;
  const s = await refreshState();
  if (!s) {
    if (store.view !== 'notguild' && store.view !== 'login') screen('📡', 'Non riesco a caricare i dati', 'Controlla la connessione e riprova.', h('button', { class: 'btn primary', type: 'button', onclick: () => location.reload() }, 'Riprova'));
    return;
  }
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
