// Stato condiviso minimale con sottoscrizioni.
export const store = {
  view: 'loading', // loading | login | notguild | app | error
  me: null, state: null, balance: 0, inVoice: false, voiceChannel: null,
  robEnd: 0, online: true, loginInfo: null,
};
const subs = new Set();
export const subscribe = (f) => { subs.add(f); return () => subs.delete(f); };
export function set(patch) { Object.assign(store, patch); subs.forEach((f) => f()); }
export function setRobCooldown(sec) { store.robEnd = Date.now() + Math.max(0, Number(sec) || 0) * 1000; }
export const robRemaining = () => Math.max(0, Math.ceil((store.robEnd - Date.now()) / 1000));
