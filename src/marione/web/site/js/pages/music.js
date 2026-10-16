// Music, laid out like Spotify: a search bar on top; below it either the results as a track list or
// the "now playing" hero and recently played covers; the queue in a side panel. The controls live in
// the player bar at the bottom of every page (see playerbar.js).
import { fill, h, ago } from '../util.js';
import { store } from '../store.js';
import { api } from '../api.js';
import { run } from '../data.js';
import { t } from '../i18n.js';
import { notice, btn, empty, progress, cover } from '../ui.js';
import { player, subscribePlayer, nowPlaying, queue, position, control, playTrack, thumbOf, clock, loadMusic } from '../player.js';

const isUrl = (s) => /^https?:\/\/\S+$/i.test(s.trim());

export function mount(root) {
  const off = h('div');
  const body = h('div', { class: 'music' });
  root.append(h('h1', { class: 'sr-only' }, t('music.title')), off, body);
  let results = null, single = false, lastQuery = '';

  // ---------- search ----------
  const q = h('input', { type: 'search', placeholder: t('music.searchPh'), 'aria-label': t('music.searchPh'), enterkeyhint: 'search', autocomplete: 'off' });
  const go = btn(t('music.search'), 'primary', { type: 'submit' });
  const clear = h('button', { type: 'button', class: 'icon-btn ms-clear', 'aria-label': t('music.clear'), title: t('music.clear'), hidden: true,
    onclick: () => { q.value = ''; clear.hidden = true; results = null; draw(); q.focus(); } }, '✕');
  q.addEventListener('input', () => { clear.hidden = !q.value; });
  const form = h('form', { class: 'ms-search', role: 'search', onsubmit: (e) => {
    e.preventDefault();
    const text = q.value.trim();
    if (!text) { q.focus(); return; }
    run(go, async () => {
      lastQuery = text;
      results = 'loading';
      draw();
      try {
        const r = await api('/api/music/search?q=' + encodeURIComponent(text));
        results = r.results; single = isUrl(text);
      } catch (err) { results = null; throw err; } finally { draw(); }
    });
  } }, h('div', { class: 'ms-box' }, h('span', { class: 'ms-ico', 'aria-hidden': 'true' }, '🔎'), q, clear), go);

  const voiceHint = h('p', { class: 'warn-box', hidden: true }, '🎧 ' + t('music.joinVoice'));
  const main = h('div', { class: 'ms-main' });
  const side = h('aside', { class: 'card ms-queue', 'aria-label': t('music.queue') });
  body.append(form, voiceHint, h('div', { class: 'ms-layout' }, main, side));

  const play = (track, now, b) => run(b, () => playTrack(track, now));

  // ---------- track list (search results) ----------
  function trackList(list) {
    return h('ol', { class: 'tl' }, list.map((tr, i) => h('li', { class: 'tl-row' },
      h('span', { class: 'tl-num' }, h('span', { class: 'tl-i' }, String(i + 1)),
        h('button', { type: 'button', class: 'tl-play', 'aria-label': t('music.playNow') + ': ' + tr.title, title: t('music.playNow'),
          onclick: (e) => play(tr, true, e.currentTarget) }, '▶')),
      cover(thumbOf(tr), 44),
      h('span', { class: 'tl-main' }, h('strong', { title: tr.title }, tr.title),
        h('small', null, [tr.channel, tr.source && tr.source !== 'youtube' ? tr.source : null].filter(Boolean).join(' · '))),
      h('span', { class: 'tl-dur' }, clock(tr.duration)),
      h('span', { class: 'tl-actions' },
        btn('▶', 'primary sm tl-now', { 'aria-label': t('music.playNow') + ': ' + tr.title, title: t('music.playNow'), onclick: (e) => play(tr, true, e.currentTarget) }),
        btn('＋', 'ghost sm', { 'aria-label': t('music.addQueue') + ': ' + tr.title, title: t('music.addQueue'), onclick: (e) => play(tr, false, e.currentTarget) })))));
  }

  // ---------- now playing hero ----------
  const hero = h('section', { class: 'ms-hero' });
  const heroBar = h('div', { class: 'ms-hero-bar' });
  function drawHero() {
    const np = nowPlaying();
    if (!np) {
      fill(hero, h('div', { class: 'ms-hero-art' }, cover(null, 168, '🎶')),
        h('div', { class: 'ms-hero-info' },
          h('span', { class: 'eyebrow' }, t('music.nowPlaying')),
          h('h2', null, t('music.silenceTitle')),
          h('p', { class: 'muted' }, t('music.silence')),
          btn('🔎 ' + t('music.find'), 'primary', { onclick: () => q.focus() })));
      hero.classList.add('idle');
      return;
    }
    hero.classList.remove('idle');
    fill(hero, h('div', { class: 'ms-hero-art' }, cover(thumbOf(np), 168)),
      h('div', { class: 'ms-hero-info' },
        h('span', { class: 'eyebrow' }, np.paused ? t('music.paused') : t('music.nowPlaying')),
        h('h2', null, h('a', { href: np.url, target: '_blank', rel: 'noopener noreferrer' }, np.title)),
        h('p', { class: 'muted' }, [np.channel, t('music.by', { name: np.requestedBy })].filter(Boolean).join(' · ')),
        heroBar,
        h('div', { class: 'ms-hero-ctl' },
          h('button', { type: 'button', class: 'big-play', 'aria-label': np.paused ? t('music.resume') : t('music.pause'),
            onclick: () => control('pause') }, np.paused ? '▶' : '⏸'),
          h('button', { type: 'button', class: 'pb-btn', 'aria-label': t('music.skip'), title: t('music.skip'), onclick: () => control('skip') }, '⏭'),
          h('button', { type: 'button', class: 'pb-btn', 'aria-label': t('music.stop'), title: t('music.stop'), onclick: () => control('stop') }, '⏹'))));
    tick();
  }
  function tick() {
    const np = nowPlaying();
    if (!np) return;
    const pos = position();
    fill(heroBar, h('span', { class: 'pb-time' }, clock(pos)), progress(np.duration ? (pos / np.duration) * 100 : 0, t('music.progress'), 'thin'),
      h('span', { class: 'pb-time' }, clock(np.duration)));
  }

  // ---------- recently played: cover cards with a play button on hover ----------
  function recentGrid() {
    const recent = ((player.st && player.st.recent) || []).slice(0, 12);
    if (!recent.length) return null;
    return h('section', { class: 'stack' }, h('h2', { class: 'ms-h' }, t('music.recent')),
      h('div', { class: 'cards' }, recent.map((tr) => h('div', { class: 'mcard' },
        h('div', { class: 'mcard-art' }, cover(thumbOf(tr), 160, '🎵', 'wide'),
          h('button', { type: 'button', class: 'mcard-play', 'aria-label': t('music.addQueue') + ': ' + tr.title, title: t('music.addQueue'),
            onclick: (e) => play({ title: tr.title, url: tr.url, duration: tr.duration }, false, e.currentTarget) }, '＋')),
        h('strong', { title: tr.title }, tr.title),
        h('small', null, [tr.by, ago(tr.at)].filter(Boolean).join(' · '))))));
  }

  // ---------- queue panel ----------
  function drawQueue() {
    const np = nowPlaying(), list = queue();
    fill(side,
      h('h2', { class: 'ms-h' }, t('music.queue')),
      np ? [h('p', { class: 'q-label' }, t('music.nowPlaying')),
        h('div', { class: 'q-row now' }, cover(thumbOf(np), 44), h('span', { class: 'q-main' }, h('strong', null, np.title), h('small', null, np.channel || '')))] : null,
      h('p', { class: 'q-label' }, t('music.next')),
      list.length ? h('ol', { class: 'q-list' }, list.map((tr, i) => h('li', { class: 'q-row' },
        h('span', { class: 'q-n' }, String(i + 1)), cover(thumbOf(tr), 40),
        h('span', { class: 'q-main' }, h('strong', { title: tr.title }, tr.title), h('small', null, t('music.by', { name: tr.requestedBy }))),
        h('button', { type: 'button', class: 'icon-btn del', 'aria-label': t('common.delete') + ': ' + tr.title, title: t('music.removeQueue'),
          onclick: () => control('remove', { index: i }) }, '✕'))))
        : empty('📭', t('music.queueEmpty')));
  }

  let shownKey = '';
  function draw() {
    const st = player.st || {};
    const key = JSON.stringify([results === 'loading' ? 'l' : results, single, st.nowPlaying && [st.nowPlaying.url, st.nowPlaying.paused], st.recent, lastQuery]);
    if (key !== shownKey) {
      shownKey = key;
      if (results === 'loading') fill(main, h('p', { class: 'muted center ms-wait' }, t('music.searching')));
      else if (results) {
        fill(main, h('div', { class: 'ms-res-head' },
          h('h2', { class: 'ms-h' }, single ? t('music.fromLink') : t('music.resultsFor', { q: lastQuery })),
          btn('✕ ' + t('music.clear'), 'ghost sm', { onclick: () => { results = null; q.value = ''; clear.hidden = true; draw(); } })),
        results.length ? h('div', { class: 'card tl-card' }, trackList(results)) : empty('🔎', t('music.noResults')));
      } else {
        drawHero();
        fill(main, hero, recentGrid());
      }
    }
    drawQueue();
  }

  const unsub = subscribePlayer(draw);
  function update() {
    const s = store.state;
    if (!s) return;
    const on = s.modules.music;
    fill(off, on ? null : notice('🔇', t('music.offTitle'), t('music.offText')));
    body.hidden = !on;
    voiceHint.hidden = store.inVoice;
    if (on && !player.st) loadMusic();
    draw();
  }
  return { update, tick, destroy() { unsub(); } };
}
