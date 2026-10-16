// Shared music state: polled while the music module is on, read by the player bar and the music page.
import { api, post } from './api.js';
import { handleError } from './data.js';
import { toast } from './toast.js';
import { t } from './i18n.js';
import { debounce } from './util.js';

export const player = { st: null, fetchedAt: 0, on: false, volTouched: 0 };
const subs = new Set();
let timer = null, lastError = null;

export const subscribePlayer = (f) => { subs.add(f); return () => subs.delete(f); };
const notify = () => subs.forEach((f) => f());

export function applyMusic(r) {
  player.st = { ...(player.st || {}), ...r };
  player.fetchedAt = Date.now();
  if (r.lastError && r.lastError !== lastError) toast(t('music.failed', { what: r.lastError.split(':')[0] }), 'err');
  lastError = r.lastError || null;
  notify();
}

export async function loadMusic() {
  try { applyMusic(await api('/api/music/state')); } catch { /* feature off or offline: keep what we have */ }
}

/** Start or stop polling (follows the music module switch). */
export function setMusicEnabled(on) {
  if (on === player.on) return;
  player.on = on;
  clearInterval(timer);
  timer = null;
  if (on) {
    loadMusic();
    timer = setInterval(() => { if (!document.hidden) loadMusic(); }, 5000);
  } else { player.st = null; notify(); }
}

export const nowPlaying = () => (player.st && player.st.nowPlaying) || null;
export const queue = () => (player.st && player.st.queue) || [];

/** Seconds into the current song, ticking locally between polls. */
export function position() {
  const np = nowPlaying();
  if (!np) return 0;
  const pos = np.paused ? np.position : np.position + (Date.now() - player.fetchedAt) / 1000;
  return np.duration ? Math.min(pos, np.duration) : pos;
}

export async function control(action, body = {}) {
  try { applyMusic(await post('/api/music/' + action, body)); } catch (e) { handleError(e); }
}

export const sendVolume = debounce(async (percent) => {
  try { await post('/api/music/volume', { percent }); } catch (e) { handleError(e); }
}, 350);

export async function playTrack(track, now) {
  const r = await post('/api/music/play', { ...track, now });
  toast(r.message);
  await loadMusic();
}

/** A cover for a track: its thumbnail, or the YouTube one guessed from the link. */
export function thumbOf(track) {
  if (!track) return null;
  if (track.thumbnail) return track.thumbnail;
  const m = /(?:[?&]v=|youtu\.be\/|\/shorts\/)([\w-]{11})/.exec(track.url || '');
  return m ? `https://i.ytimg.com/vi/${m[1]}/mqdefault.jpg` : null;
}

export function clock(s) {
  if (s == null) return '—';
  const v = Math.max(0, Math.round(s));
  const hh = Math.floor(v / 3600), mm = Math.floor((v % 3600) / 60), ss = v % 60;
  const p = (x) => String(x).padStart(2, '0');
  return hh ? `${hh}:${p(mm)}:${p(ss)}` : `${mm}:${p(ss)}`;
}
