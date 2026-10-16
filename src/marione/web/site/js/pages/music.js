// Music: what is playing, search (10 results to pick from, or a link), the queue, recent songs.
import { fill, h, ago, debounce } from '../util.js';
import { store } from '../store.js';
import { api, post } from '../api.js';
import { run, handleError } from '../data.js';
import { toast } from '../toast.js';
import { t } from '../i18n.js';
import { card, cardTitle, pageHead, notice, btn, empty, progress } from '../ui.js';

const clock = (s) => {
  if (s == null) return '—';
  const v = Math.max(0, Math.round(s));
  const hh = Math.floor(v / 3600), mm = Math.floor((v % 3600) / 60), ss = v % 60;
  const p = (x) => String(x).padStart(2, '0');
  return hh ? `${hh}:${p(mm)}:${p(ss)}` : `${mm}:${p(ss)}`;
};
const isUrl = (s) => /^https?:\/\/\S+$/i.test(s.trim());

function cover(track, size = 64) {
  const box = h('span', { class: 'cover', style: { width: size + 'px', height: size + 'px' }, 'aria-hidden': 'true' }, '🎵');
  if (track && track.thumbnail) {
    const img = h('img', { src: track.thumbnail, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
    img.addEventListener('error', () => img.remove());
    box.append(img);
  }
  return box;
}

export function mount(root) {
  root.append(pageHead(t('music.title'), t('music.sub')));
  const off = h('div');
  const body = h('div', { class: 'stack-lg' });
  root.append(off, body);
  let st = null, fetchedAt = 0, timer = null, volTouched = 0, lastError = null;

  // ---------- now playing ----------
  const now = card('now-playing');
  const volOut = h('output', { class: 'vol-out' }, '50%');
  const vol = h('input', { type: 'range', min: '0', max: '100', step: '1', value: '50', 'aria-label': t('music.volume') });
  const sendVol = debounce(async () => {
    try { await post('/api/music/volume', { percent: Number(vol.value) }); } catch (e) { handleError(e); }
  }, 350);
  vol.addEventListener('input', () => { volOut.textContent = vol.value + '%'; volTouched = Date.now(); sendVol(); });
  const control = (action, b) => run(b, async () => { apply(await post('/api/music/' + action, {})); });
  const pauseBtn = btn('⏯', 'round-btn', { 'aria-label': t('music.pause'), title: t('music.pause'), onclick: (e) => control('pause', e.currentTarget) });
  const skipBtn = btn('⏭', 'round-btn', { 'aria-label': t('music.skip'), title: t('music.skip'), onclick: (e) => control('skip', e.currentTarget) });
  const stopBtn = btn('⏹', 'round-btn danger', { 'aria-label': t('music.stop'), title: t('music.stop'), onclick: (e) => control('stop', e.currentTarget) });
  const nowBody = h('div', { class: 'np-body' });
  const posText = h('span', { class: 'np-time' });
  const bar = h('div', { class: 'np-bar' });
  now.append(cardTitle('🎧', t('music.nowPlaying')), nowBody, bar,
    h('div', { class: 'np-controls' }, pauseBtn, skipBtn, stopBtn,
      h('label', { class: 'vol' }, h('span', { class: 'field-label' }, '🔈'), vol, volOut)));

  function drawNow() {
    const np = st && st.nowPlaying;
    pauseBtn.disabled = skipBtn.disabled = stopBtn.disabled = !np;
    if (!np) {
      fill(nowBody, empty('🎶', t('music.silence')));
      fill(bar);
      return;
    }
    pauseBtn.textContent = np.paused ? '▶' : '⏸';
    pauseBtn.setAttribute('aria-label', np.paused ? t('music.resume') : t('music.pause'));
    fill(nowBody, cover(np, 96),
      h('div', { class: 'np-info' },
        h('a', { class: 'np-title', href: np.url, target: '_blank', rel: 'noopener noreferrer' }, np.title),
        h('small', null, [np.channel, t('music.by', { name: np.requestedBy })].filter(Boolean).join(' · ')),
        np.paused ? h('span', { class: 'tag' }, t('music.paused')) : null));
    tickBar();
  }
  function tickBar() {
    const np = st && st.nowPlaying;
    if (!np) return;
    const pos = np.paused ? np.position : np.position + (Date.now() - fetchedAt) / 1000;
    const pct = np.duration ? (pos / np.duration) * 100 : 0;
    posText.textContent = clock(Math.min(pos, np.duration || pos)) + ' / ' + clock(np.duration);
    fill(bar, progress(pct, t('music.progress')), posText);
  }

  // ---------- search ----------
  const q = h('input', { type: 'search', placeholder: t('music.searchPh'), 'aria-label': t('music.searchPh'), enterkeyhint: 'search', autocomplete: 'off' });
  const go = btn('🔎 ' + t('music.search'), 'primary', { type: 'submit' });
  const results = h('div', { class: 'stack' });
  const searchForm = h('form', { class: 'search-row', onsubmit: (e) => {
    e.preventDefault();
    const text = q.value.trim();
    if (!text) { q.focus(); return; }
    run(go, async () => {
      fill(results, h('p', { class: 'muted center' }, t('music.searching')));
      try {
        const r = await api('/api/music/search?q=' + encodeURIComponent(text));
        drawResults(r.results, isUrl(text));
      } catch (err) { fill(results); throw err; }
    });
  } }, h('div', { class: 'search' }, h('span', { class: 'search-ico', 'aria-hidden': 'true' }, '🎵'), q), go);

  const play = async (track, now, b) => run(b, async () => {
    const r = await post('/api/music/play', { ...track, now });
    toast(r.message);
    await load();
  });
  function trackRow(track, actions) {
    return h('li', { class: 'track' }, cover(track, 56),
      h('span', { class: 'track-main' }, h('strong', null, track.title),
        h('small', null, [track.channel, clock(track.duration), track.source && track.source !== 'youtube' ? track.source : null].filter(Boolean).join(' · '))),
      h('span', { class: 'track-actions' }, actions));
  }
  function drawResults(list, single) {
    if (!list.length) { fill(results, empty('🔎', t('music.noResults'))); return; }
    fill(results, h('p', { class: 'muted small' }, single ? t('music.fromLink') : t('music.pick')),
      h('ul', { class: 'tracks' }, list.map((tr) => trackRow(tr, [
        btn('▶ ' + t('music.playNow'), 'primary sm', { onclick: (e) => play(tr, true, e.currentTarget) }),
        btn('＋ ' + t('music.addQueue'), 'ghost sm', { onclick: (e) => play(tr, false, e.currentTarget) }),
      ]))));
    // On a phone the results start below the fold: bring them into view.
    if (window.innerWidth < 800) results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  const searchCard = card('', cardTitle('🔎', t('music.find')), h('p', { class: 'hint' }, t('music.findHint')), searchForm, results);

  // ---------- queue + recent ----------
  const queueBody = h('div');
  const recentBody = h('div');
  const queueCard = card('', cardTitle('📜', t('music.queue')), queueBody);
  const recentCard = h('details', { class: 'card fold' },
    h('summary', null, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, '🕘'),
      h('span', { class: 'fold-title' }, h('h2', null, t('music.recent')), h('small', null, t('music.recentSub'))),
      h('span', { class: 'fold-chev', 'aria-hidden': 'true' }, '▾')),
    h('div', { class: 'fold-body' }, recentBody));
  function drawQueue() {
    const list = (st && st.queue) || [];
    fill(queueBody, list.length ? h('ol', { class: 'tracks numbered' }, list.map((tr, i) => trackRow(tr, [
      h('small', { class: 'muted' }, t('music.by', { name: tr.requestedBy })),
      h('button', { type: 'button', class: 'icon-btn del', 'aria-label': t('common.delete') + ' ' + tr.title, title: t('common.delete'),
        onclick: (e) => run(e.currentTarget, async () => { apply(await post('/api/music/remove', { index: i })); }) }, '🗑'),
    ]))) : empty('📭', t('music.queueEmpty')));
    const recent = (st && st.recent) || [];
    fill(recentBody, recent.length ? h('ul', { class: 'tracks' }, recent.map((tr) => trackRow(tr, [
      h('small', { class: 'muted' }, [tr.by, ago(tr.at)].filter(Boolean).join(' · ')),
      btn('＋', 'ghost sm', { 'aria-label': t('music.addQueue') + ': ' + tr.title, title: t('music.addQueue'), onclick: (e) => play({ title: tr.title, url: tr.url, duration: tr.duration }, false, e.currentTarget) }),
    ]))) : empty('🕘', t('music.noRecent')));
  }

  const voiceHint = h('p', { class: 'warn-box', hidden: true }, '🎧 ' + t('music.joinVoice'));
  body.append(voiceHint, h('div', { class: 'grid g-music' }, now, searchCard), queueCard, recentCard);

  function apply(r) {
    st = { ...(st || {}), ...r };
    fetchedAt = Date.now();
    if (Date.now() - volTouched > 3000 && document.activeElement !== vol && r.volume != null) { vol.value = r.volume; volOut.textContent = r.volume + '%'; }
    drawNow(); drawQueue();
    if (r.lastError && r.lastError !== lastError) toast(t('music.failed', { what: r.lastError.split(':')[0] }), 'err');
    lastError = r.lastError || null;
  }
  async function load() {
    try { apply(await api('/api/music/state')); } catch (e) { if (e.code !== 'feature_off') handleError(e); }
  }

  function update() {
    const s = store.state;
    if (!s) return;
    const on = s.modules.music;
    fill(off, on ? null : notice('🔇', t('music.offTitle'), t('music.offText')));
    body.hidden = !on;
    voiceHint.hidden = store.inVoice;
    if (on && !timer) { load(); timer = setInterval(() => { if (!document.hidden) load(); }, 5000); }
  }
  return { update, tick: tickBar, destroy() { clearInterval(timer); sendVol.cancel(); } };
}

