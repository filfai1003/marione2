// Music, laid out like Spotify: a search bar on top, then three tabs. "Listen" is the search results or
// the "now playing" hero and recently played covers; "Library" holds the mp3 files uploaded to the
// server; "Playlists" are named lists of songs. The queue sits in a side panel. The controls live in
// the player bar at the bottom of every page (see playerbar.js).
import { fill, h, ago } from '../util.js';
import { store } from '../store.js';
import { api, post } from '../api.js';
import { run, handleError } from '../data.js';
import { toast } from '../toast.js';
import { t } from '../i18n.js';
import { notice, btn, empty, progress, cover, tabs, nameModal, confirmDialog, pickFile, popover, preview } from '../ui.js';
import { player, subscribePlayer, nowPlaying, queue, position, control, playTrack, thumbOf, clock, loadMusic, applyMusic } from '../player.js';

const isUrl = (s) => /^https?:\/\/\S+$/i.test(s.trim());
const LIB_MAX = 24 * 1024 * 1024;
const mb = (bytes) => (bytes < 1024 * 1024 ? Math.max(1, Math.round(bytes / 1024)) + ' KB' : (bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0) + ' MB');
/** The part of a track the server needs to play it or put it in a playlist. */
const pick = (tr) => ({ title: tr.title, url: tr.url, duration: tr.duration, channel: tr.channel, thumbnail: tr.thumbnail });

export function mount(root) {
  const off = h('div');
  const body = h('div', { class: 'music' });
  root.append(h('h1', { class: 'sr-only' }, t('music.title')), off, body);
  let results = null, single = false, lastQuery = '';
  let view = 'now';
  let library = null;   // {tracks, count, usedBytes, …} once loaded
  let lists = null;     // [playlist] once loaded
  let openId = null, detail = null; // the playlist being looked at

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
      showTab('now');
      try {
        const r = await api('/api/music/search?q=' + encodeURIComponent(text));
        results = r.results; single = isUrl(text);
      } catch (err) { results = null; throw err; } finally { draw(); }
    });
  } }, h('div', { class: 'ms-box' }, h('span', { class: 'ms-ico', 'aria-hidden': 'true' }, '🔎'), q, clear), go);

  const voiceHint = h('p', { class: 'warn-box', hidden: true }, '🎧 ' + t('music.joinVoice'));
  const main = h('div', { class: 'ms-main' });
  const side = h('aside', { class: 'card ms-queue', 'aria-label': t('music.queue') });
  const tabBar = tabs([['now', '🎶', t('music.tabNow')], ['library', '📚', t('music.tabLibrary')], ['playlists', '🎼', t('music.tabPlaylists')]],
    view, (k) => showTab(k, true));
  body.append(form, voiceHint, tabBar.el, h('div', { class: 'ms-layout' }, main, side));

  function showTab(k, fromTab) {
    view = k;
    if (!fromTab) tabBar.select(k);
    if (k === 'library' && !library) loadLibrary();
    if (k === 'playlists' && !lists) loadLists();
    draw();
  }

  const play = (track, now, b) => run(b, () => playTrack(track, now));

  // ---------- data ----------
  async function loadLibrary() {
    try { library = await api('/api/music/library'); } catch (e) { handleError(e); }
    draw();
  }
  async function loadLists() {
    try { lists = (await api('/api/music/playlists')).playlists; } catch (e) { handleError(e); }
    draw();
  }
  async function loadOpen() {
    if (!openId) return;
    try { detail = await api('/api/music/playlist?id=' + encodeURIComponent(openId)); } catch (e) {
      openId = null; detail = null; handleError(e); await loadLists();
    }
    draw();
  }

  // ---------- playlists: create, choose, add ----------
  function newPlaylist(track) {
    nameModal({
      title: t('music.pl.new'), name: '', withEmoji: false, maxLength: 60, okLabel: t('common.save'),
      onSubmit: async ({ name }) => {
        try {
          await post('/api/music/playlist/create', { name, ...(track ? { track: pick(track) } : {}) });
          toast(t('music.pl.created', { name }));
          await loadLists();
          if (openId) await loadOpen();
        } catch (e) { handleError(e); return false; }
        return true;
      },
    });
  }
  async function addToPlaylist(track, anchor) {
    if (!lists) await loadLists();
    const mine = (lists || []).filter((p) => p.own);
    popover(anchor, [
      ...mine.map((p) => ['🎼', p.name, async () => {
        try {
          const r = await post('/api/music/playlist/add', { id: p.id, track: pick(track) });
          toast(r.message);
          lists = null; await loadLists();
          if (openId === p.id) await loadOpen();
        } catch (e) { handleError(e); }
      }]),
      ['＋', t('music.pl.new'), () => newPlaylist(track)],
    ]);
  }
  const playList = (p, opts, b) => run(b, async () => {
    const r = await post('/api/music/playlist/play', { id: p.id, ...opts });
    applyMusic(r);
    toast(r.message);
  });
  async function openList(id) {
    openId = id; detail = null; draw();
    await loadOpen();
  }
  const closeList = () => { openId = null; detail = null; draw(); };

  // ---------- library: upload, rename, delete ----------
  function openUpload(file) {
    const okType = file.type ? file.type.startsWith('audio/') : /\.(mp3|wav|ogg)$/i.test(file.name);
    if (!okType) { toast(t('file.notAudio'), 'err'); return; }
    if (file.size > LIB_MAX) { toast(t('music.lib.tooBig'), 'err'); return; }
    nameModal({
      title: t('music.lib.uploadTitle'), file, name: file.name.replace(/\.[^.]+$/, '').slice(0, 200), withEmoji: false, maxLength: 200,
      okLabel: t('music.lib.upload'),
      onSubmit: async ({ name }) => {
        const fd = new FormData();
        fd.append('name', name);
        fd.append('file', file);
        try {
          await api('/api/music/library/add', { method: 'POST', form: fd });
          toast(t('music.lib.added', { name }));
          await loadLibrary();
        } catch (e) { handleError(e); return false; }
        return true;
      },
    });
  }
  const upId = (tr) => tr.url.replace('upload:', '');
  function libraryMore(tr, anchor) {
    const id = upId(tr), key = 'm' + id, canEdit = tr.own || store.me.isAdmin;
    const listening = preview.key() === key;
    popover(anchor, [
      ['🎼', t('music.pl.addTo'), () => addToPlaylist(tr, anchor)],
      [listening ? '⏸' : '🎧', listening ? t('music.stopListen') : t('music.listenHere'),
        () => preview.toggle(key, '/api/music/library/audio?id=' + encodeURIComponent(id), () => toast(t('board.noPreview'), 'err'))],
      ['⬇️', t('music.download'), () => {
        const a = h('a', { href: '/api/music/library/audio?download=1&id=' + encodeURIComponent(id), download: '' });
        document.body.append(a); a.click(); a.remove();
      }],
      canEdit ? ['✏️', t('music.rename'), () => nameModal({
        title: t('music.rename'), name: tr.title, withEmoji: false, maxLength: 200, okLabel: t('common.save'),
        onSubmit: async ({ name }) => {
          try { await post('/api/music/library/rename', { id, title: name }); toast(t('music.renamed')); await loadLibrary(); }
          catch (e) { handleError(e); return false; }
          return true;
        },
      })] : null,
      canEdit ? ['🗑', t('common.delete'), () => confirmDialog(t('music.lib.delTitle'), t('music.lib.delText', { name: tr.title }), t('common.delete') + ' 🗑', async (b) => {
        await run(b, async () => { await post('/api/music/library/remove', { id }); toast(t('music.lib.deleted')); lists = null; await loadLibrary(); });
      }), 'danger'] : null,
    ]);
  }

  // ---------- track list (search results, library, playlist) ----------
  // opts: {playlist: add-to-playlist button, more(tr, anchor): "⋯" menu, remove(tr, button): "✕" button}
  function trackList(list, opts = {}) {
    return h('ol', { class: 'tl' }, list.map((tr, i) => h('li', { class: 'tl-row' },
      h('span', { class: 'tl-num' }, h('span', { class: 'tl-i' }, String(i + 1)),
        h('button', { type: 'button', class: 'tl-play', 'aria-label': t('music.playNow') + ': ' + tr.title, title: t('music.playNow'),
          onclick: (e) => play(tr, true, e.currentTarget) }, '▶')),
      cover(thumbOf(tr), 44),
      h('span', { class: 'tl-main' }, h('strong', { title: tr.title }, tr.title),
        h('small', null, [tr.channel, tr.source && !['youtube', 'upload'].includes(tr.source) ? tr.source : null].filter(Boolean).join(' · '))),
      h('span', { class: 'tl-dur' }, clock(tr.duration)),
      h('span', { class: 'tl-actions' },
        btn('▶', 'primary sm tl-now', { 'aria-label': t('music.playNow') + ': ' + tr.title, title: t('music.playNow'), onclick: (e) => play(tr, true, e.currentTarget) }),
        btn('＋', 'ghost sm', { 'aria-label': t('music.addQueue') + ': ' + tr.title, title: t('music.addQueue'), onclick: (e) => play(tr, false, e.currentTarget) }),
        opts.playlist ? btn('🎼', 'ghost sm', { 'aria-label': t('music.pl.addTo') + ': ' + tr.title, title: t('music.pl.addTo'),
          'aria-haspopup': 'menu', 'aria-expanded': 'false', onclick: (e) => addToPlaylist(tr, e.currentTarget) }) : null,
        opts.more ? btn('⋯', 'ghost sm', { 'aria-label': t('music.more', { name: tr.title }), title: t('music.more', { name: tr.title }),
          'aria-haspopup': 'menu', 'aria-expanded': 'false', onclick: (e) => opts.more(tr, e.currentTarget) }) : null,
        opts.remove ? btn('✕', 'ghost sm', { 'aria-label': t('music.pl.removeTrack') + ': ' + tr.title, title: t('music.pl.removeTrack'),
          onclick: (e) => opts.remove(tr, e.currentTarget) }) : null))));
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
    const title = np.url.startsWith('http') ? h('a', { href: np.url, target: '_blank', rel: 'noopener noreferrer' }, np.title) : np.title;
    fill(hero, h('div', { class: 'ms-hero-art' }, cover(thumbOf(np), 168)),
      h('div', { class: 'ms-hero-info' },
        h('span', { class: 'eyebrow' }, np.paused ? t('music.paused') : t('music.nowPlaying')),
        h('h2', null, title),
        h('p', { class: 'muted' }, [np.channel, t('music.by', { name: np.requestedBy })].filter(Boolean).join(' · ')),
        heroBar,
        h('div', { class: 'ms-hero-ctl' },
          h('button', { type: 'button', class: 'big-play', 'aria-label': np.paused ? t('music.resume') : t('music.pause'),
            onclick: () => control('pause') }, np.paused ? '▶' : '⏸'),
          h('button', { type: 'button', class: 'pb-btn', 'aria-label': t('music.skip'), title: t('music.skip'), onclick: () => control('skip') }, '⏭'),
          h('button', { type: 'button', class: 'pb-btn', 'aria-label': t('music.stop'), title: t('music.stop'), onclick: () => control('stop') }, '⏹'),
          h('button', { type: 'button', class: 'pb-btn', 'aria-label': t('music.pl.addTo'), title: t('music.pl.addTo'), 'aria-haspopup': 'menu', 'aria-expanded': 'false',
            onclick: (e) => addToPlaylist(np, e.currentTarget) }, '🎼'))));
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

  // ---------- library tab ----------
  function libraryView() {
    const head = h('div', { class: 'ms-res-head' },
      h('div', null, h('h2', { class: 'ms-h' }, t('music.tabLibrary')), h('p', { class: 'muted small' }, t('music.lib.sub')),
        library ? h('p', { class: 'muted small' }, t('music.lib.usage', { count: library.count, used: mb(library.usedBytes), max: mb(library.maxBytes) })) : null),
      btn('＋ ' + t('music.lib.upload'), 'primary', { onclick: () => pickFile(openUpload) }));
    if (!library) return [head, h('p', { class: 'muted center ms-wait' }, t('music.searching'))];
    return [head, library.tracks.length
      ? h('div', { class: 'card tl-card' }, trackList(library.tracks, { playlist: true, more: libraryMore }))
      : empty('📚', t('music.lib.empty'))];
  }

  // ---------- playlists tab ----------
  function playlistCard(p) {
    return h('button', { type: 'button', class: 'mcard pl-card', onclick: () => openList(p.id) },
      h('div', { class: 'mcard-art' }, cover(null, 160, '🎼', 'wide')),
      h('strong', { title: p.name }, p.name),
      h('small', null, [t('music.pl.count', { count: p.count }), p.count && p.duration ? clock(p.duration) : null, !p.own && p.owner ? t('music.pl.by', { name: p.owner }) : null].filter(Boolean).join(' · ')));
  }
  function playlistsView() {
    if (openId) return detail ? detailView() : [h('p', { class: 'muted center ms-wait' }, t('music.searching'))];
    const head = h('div', { class: 'ms-res-head' }, h('h2', { class: 'ms-h' }, t('music.tabPlaylists')),
      btn('＋ ' + t('music.pl.new'), 'primary', { onclick: () => newPlaylist(null) }));
    if (!lists) return [head, h('p', { class: 'muted center ms-wait' }, t('music.searching'))];
    if (!lists.length) return [head, empty('🎼', t('music.pl.empty'))];
    const mine = lists.filter((p) => p.own), others = lists.filter((p) => !p.own);
    return [head,
      mine.length ? h('section', { class: 'stack' }, others.length ? h('h3', { class: 'q-label' }, t('music.pl.mine')) : null, h('div', { class: 'cards' }, mine.map(playlistCard))) : null,
      others.length ? h('section', { class: 'stack' }, h('h3', { class: 'q-label' }, t('music.pl.others')), h('div', { class: 'cards' }, others.map(playlistCard))) : null];
  }
  function detailView() {
    const p = detail.playlist, tracks = detail.tracks, canEdit = p.own || store.me.isAdmin;
    const removeItem = (tr, b) => run(b, async () => {
      await post('/api/music/playlist/remove', { id: p.id, itemId: tr.itemId });
      lists = null; await loadOpen(); loadLists();
    });
    return [
      h('div', { class: 'ms-res-head' }, btn('‹ ' + t('music.pl.back'), 'ghost sm', { onclick: closeList }),
        canEdit ? h('span', { class: 'tl-actions' },
          btn('✏️', 'ghost sm', { 'aria-label': t('music.pl.rename'), title: t('music.pl.rename'), onclick: () => nameModal({
            title: t('music.pl.rename'), name: p.name, withEmoji: false, maxLength: 60, okLabel: t('common.save'),
            onSubmit: async ({ name }) => {
              try { await post('/api/music/playlist/rename', { id: p.id, name }); lists = null; await loadOpen(); loadLists(); }
              catch (e) { handleError(e); return false; }
              return true;
            } }) }),
          btn('🗑', 'ghost sm', { 'aria-label': t('music.pl.delete'), title: t('music.pl.delete'), onclick: () => confirmDialog(
            t('music.pl.delTitle'), t('music.pl.delText', { name: p.name }), t('common.delete') + ' 🗑', async (b) => {
              await run(b, async () => { await post('/api/music/playlist/delete', { id: p.id }); toast(t('music.pl.deleted')); openId = null; detail = null; lists = null; await loadLists(); });
            }) })) : null),
      h('section', { class: 'pl-head' }, cover(null, 120, '🎼'),
        h('div', { class: 'stack' }, h('h2', { class: 'ms-h' }, p.name),
          h('p', { class: 'muted' }, [t('music.pl.count', { count: p.count }), p.duration ? clock(p.duration) : null, p.owner ? t('music.pl.by', { name: p.owner }) : null].filter(Boolean).join(' · ')),
          p.count ? h('div', { class: 'pl-btns' },
            btn('▶ ' + t('music.pl.play'), 'primary', { onclick: (e) => playList(p, { replace: true }, e.currentTarget) }),
            btn('🔀 ' + t('music.pl.shuffle'), 'ghost', { onclick: (e) => playList(p, { replace: true, shuffle: true }, e.currentTarget) }),
            btn('＋ ' + t('music.pl.queue'), 'ghost', { onclick: (e) => playList(p, {}, e.currentTarget) })) : null)),
      tracks.length ? h('div', { class: 'card tl-card' }, trackList(tracks, { remove: canEdit ? removeItem : null })) : empty('🎼', t('music.pl.noSongs')),
    ];
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
    const key = JSON.stringify([view, results === 'loading' ? 'l' : results, single, st.nowPlaying && [st.nowPlaying.url, st.nowPlaying.paused],
      view === 'now' ? st.recent : null, lastQuery, view === 'library' ? library : null, view === 'playlists' ? [lists, openId, detail] : null]);
    if (key !== shownKey) {
      shownKey = key;
      if (view === 'library') fill(main, libraryView());
      else if (view === 'playlists') fill(main, playlistsView());
      else if (results === 'loading') fill(main, h('p', { class: 'muted center ms-wait' }, t('music.searching')));
      else if (results) {
        fill(main, h('div', { class: 'ms-res-head' },
          h('h2', { class: 'ms-h' }, single ? t('music.fromLink') : t('music.resultsFor', { q: lastQuery })),
          btn('✕ ' + t('music.clear'), 'ghost sm', { onclick: () => { results = null; q.value = ''; clear.hidden = true; draw(); } })),
        results.length ? h('div', { class: 'card tl-card' }, trackList(results, { playlist: true })) : empty('🔎', t('music.noResults')));
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
  return { update, tick, drop: openUpload, destroy() { unsub(); preview.stop(); } };
}
