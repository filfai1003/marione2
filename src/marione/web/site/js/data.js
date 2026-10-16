// State fetching, polling and shared error handling.
import { api, ApiError } from './api.js';
import { store, set, setRobCooldown } from './store.js';
import { toast } from './toast.js';
import { t } from './i18n.js';

export function applyState(s) {
  setRobCooldown(s.rob ? s.rob.cooldownSeconds : 0);
  set({ state: s, me: { ...store.me, ...s.me }, balance: s.balance, inVoice: s.inVoice, voiceChannel: s.voiceChannel });
}

export async function refreshState() {
  try {
    const s = await api('/api/state');
    applyState(s);
    return s;
  } catch (e) {
    if (e.code === 'not_in_guild') set({ view: 'notguild' });
    return null;
  }
}

async function refreshLive() {
  try {
    const l = await api('/api/live');
    setRobCooldown(l.robCooldownSeconds);
    set({ balance: l.balance, inVoice: l.inVoice, voiceChannel: l.voiceChannel });
  } catch { /* offline: tieni gli ultimi dati */ }
}

export function setBalance(b) { if (typeof b === 'number') set({ balance: b }); }

/** Toast dell'errore del server; aggiorna cooldown/stato quando serve. */
export function handleError(e, overrides = {}) {
  if (!(e instanceof ApiError)) { toast(t('common.unexpected'), 'err'); return; }
  if (e.code === 'unauthorized') return;
  if (e.code === 'cooldown') setRobCooldown(e.cooldownSeconds);
  if (e.code === 'feature_off') refreshState();
  toast(overrides[e.code] || e.message, 'err');
}

/** Esegue `fn` disabilitando il bottone mentre la richiesta è in corso (niente doppio invio). */
export async function run(btn, fn) {
  if (btn.disabled || btn.dataset.busy) return undefined;
  btn.dataset.busy = '1';
  btn.disabled = true;
  btn.classList.add('busy');
  try { return await fn(); } catch (e) { handleError(e); return undefined; }
  finally { delete btn.dataset.busy; btn.classList.remove('busy'); btn.disabled = false; }
}

let timers = [];
export function stopPolling() { timers.forEach(clearInterval); timers = []; }
export function startPolling() {
  stopPolling();
  timers.push(setInterval(() => { if (!document.hidden) refreshState(); }, 15000));
  timers.push(setInterval(() => { if (!document.hidden) refreshLive(); }, 5000));
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && store.view === 'app') { refreshState(); refreshLive(); }
});
