// The player bar: always at the bottom while a song is on (like Spotify), on every page.
// Desktop: song · controls with progress · volume and queue. Phone: a mini player above the tabs.
import { h, fill } from './util.js';
import { t } from './i18n.js';
import { cover, progress } from './ui.js';
import { player, subscribePlayer, nowPlaying, queue, position, control, sendVolume, thumbOf, clock } from './player.js';

export function playerBar() {
  const art = h('a', { class: 'pb-art', href: '#/music', 'aria-label': t('music.openPlayer') });
  const title = h('a', { class: 'pb-title', href: '#/music' });
  const sub = h('small', { class: 'pb-sub' });
  const ib = (txt, label, fn, cls = '') => h('button', { type: 'button', class: 'pb-btn ' + cls, 'aria-label': label, title: label, onclick: fn }, txt);
  const playBtn = ib('⏸', t('music.pause'), () => control('pause'), 'main');
  const skipBtn = ib('⏭', t('music.skip'), () => control('skip'));
  const stopBtn = ib('⏹', t('music.stop'), () => control('stop'), 'hide-sm');
  const tNow = h('span', { class: 'pb-time' }), tEnd = h('span', { class: 'pb-time' });
  const bar = h('div', { class: 'pb-progress' });
  const vol = h('input', { type: 'range', min: '0', max: '100', step: '1', value: '50', 'aria-label': t('music.volume') });
  vol.addEventListener('input', () => { player.volTouched = Date.now(); sendVolume(Number(vol.value)); });
  const queueLink = h('a', { class: 'pb-btn', href: '#/music', 'aria-label': t('music.queue'), title: t('music.queue') }, '☰');
  const count = h('span', { class: 'pb-count' });
  const el = h('div', { class: 'playerbar', role: 'region', 'aria-label': t('music.nowPlaying'), hidden: true },
    h('div', { class: 'pb-song' }, art, h('div', { class: 'pb-text' }, title, sub)),
    h('div', { class: 'pb-center' },
      h('div', { class: 'pb-controls' }, stopBtn, playBtn, skipBtn),
      h('div', { class: 'pb-line' }, tNow, bar, tEnd)),
    h('div', { class: 'pb-right' }, h('span', { 'aria-hidden': 'true' }, '🔈'), vol, h('span', { class: 'pb-q' }, queueLink, count)));
  let key = '';

  function draw() {
    const np = nowPlaying();
    el.hidden = !player.on || !np;
    document.body.classList.toggle('has-player', !el.hidden);
    if (!np) return;
    const k = JSON.stringify([np.url, np.title, np.paused, np.requestedBy, queue().length]);
    if (k !== key) {
      key = k;
      fill(art, cover(thumbOf(np), 56));
      title.textContent = np.title;
      title.title = np.title;
      sub.textContent = [np.channel, t('music.by', { name: np.requestedBy })].filter(Boolean).join(' · ');
      playBtn.textContent = np.paused ? '▶' : '⏸';
      playBtn.setAttribute('aria-label', np.paused ? t('music.resume') : t('music.pause'));
      playBtn.title = playBtn.getAttribute('aria-label');
      const n = queue().length;
      count.textContent = n ? String(n) : '';
      count.hidden = !n;
    }
    const st = player.st || {};
    if (Date.now() - player.volTouched > 3000 && document.activeElement !== vol && st.volume != null) vol.value = st.volume;
    tick();
  }
  function tick() {
    const np = nowPlaying();
    if (!np || el.hidden) return;
    const pos = position();
    tNow.textContent = clock(pos);
    tEnd.textContent = clock(np.duration);
    fill(bar, progress(np.duration ? (pos / np.duration) * 100 : 0, t('music.progress'), 'thin'));
  }
  const unsub = subscribePlayer(draw);
  const timer = setInterval(() => { if (!document.hidden) tick(); }, 1000);
  draw();
  return { el, destroy() { unsub(); clearInterval(timer); } };
}
