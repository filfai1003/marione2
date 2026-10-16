// Soundboard: search + filters over a compact grid, sticky volume bar, favourites first.
import { h, region, fmtDur, debounce, fileBase, checkAudio } from '../util.js';
import { store } from '../store.js';
import { api, post } from '../api.js';
import { run, refreshState, handleError } from '../data.js';
import { toast } from '../toast.js';
import { t, locale } from '../i18n.js';
import { pageHead, notice, btn, nameModal, confirmDialog, pickFile, searchBox, chipGroup, empty, preview } from '../ui.js';

/** Upload modal for a file (also used by the global drag & drop). */
export function openAdd(file) {
  const err = checkAudio(file);
  if (err) { toast(err, 'err'); return; }
  nameModal({
    title: t('board.newSound'), file, name: fileBase(file.name), withEmoji: true, okLabel: t('board.add') + ' 🔊',
    onSubmit: async ({ name, emoji }) => {
      const fd = new FormData();
      fd.append('name', name);
      if (emoji) fd.append('emoji', emoji);
      fd.append('file', file);
      try {
        await api('/api/soundboard/add', { method: 'POST', form: fd });
        toast(t('board.added', { name }));
        await refreshState();
      } catch (e) { handleError(e); return false; }
      return true;
    },
  });
}

export function mount(root) {
  root.append(pageHead(t('board.title'), t('board.sub')));
  const off = h('div'), body = h('div', { class: 'stack' });
  root.append(off, body);
  let filter = 'all', query = '';
  let sort = 'name';
  try { sort = localStorage.getItem('marione-board-sort') || 'name'; } catch { /* storage blocked */ }

  // ---- sticky controls: volume, stop, search, filters, add ----
  const volOut = h('output', { class: 'vol-out' }, '80%');
  const vol = h('input', { type: 'range', min: '0', max: '100', step: '1', value: '80', 'aria-label': t('board.volume') });
  let volTouched = 0;
  const sendVol = debounce(async () => {
    try { await post('/api/soundboard/volume', { percent: Number(vol.value) }); } catch (e) { handleError(e); }
  }, 350);
  vol.addEventListener('input', () => { volOut.textContent = vol.value + '%'; volTouched = Date.now(); sendVol(); });
  const stopBtn = btn('⏹ ' + t('board.stop'), 'danger sm', { onclick: () => run(stopBtn, () => post('/api/soundboard/stop')) });
  const addBtn = btn('＋ ' + t('board.add'), 'primary sm', { onclick: () => pickFile(openAdd) });
  const search = searchBox(t('board.search'), (q) => { query = q.toLowerCase(); draw(); }, 120);
  const chips = chipGroup([['all', t('board.fAll')], ['fav', '★ ' + t('board.fFav')], ['mine', t('board.fMine')]], filter,
    (k) => { filter = k; draw(); }, t('board.filter'));
  const sortSel = h('select', { class: 'sort-pick', 'aria-label': t('board.sort') },
    [['name', t('board.sortName')], ['short', t('board.sortShort')], ['long', t('board.sortLong')]].map(([v, l]) =>
      h('option', { value: v, selected: v === sort }, l)));
  sortSel.addEventListener('change', () => {
    sort = sortSel.value;
    try { localStorage.setItem('marione-board-sort', sort); } catch { /* storage blocked */ }
    draw();
  });
  const bar = h('div', { class: 'card controls sticky' },
    h('div', { class: 'controls-row' },
      h('label', { class: 'vol' }, h('span', { class: 'field-label' }, '🔈 ' + t('board.volume')), vol, volOut), stopBtn),
    h('div', { class: 'controls-row' }, search.el, chips, h('label', { class: 'sort' }, h('span', { class: 'field-label' }, '↕ ' + t('board.sort')), sortSel), addBtn));
  const count = h('p', { class: 'muted small', 'aria-live': 'polite' });
  const grid = h('div');
  body.append(bar, count, grid);

  const play = async (s, tile) => {
    tile.classList.remove('pulse'); void tile.offsetWidth; tile.classList.add('pulse');
    try { await post('/api/soundboard/play', { id: s.id }); } catch (e) { handleError(e); }
  };
  const toggleFav = (s, b) => run(b, async () => { await post('/api/soundboard/favorite', { id: s.id }); await refreshState(); });
  const rename = (s) => nameModal({
    title: t('board.edit'), name: s.name, emoji: s.emoji, withEmoji: true, okLabel: t('common.save'),
    onSubmit: async ({ name, emoji }) => {
      try { await post('/api/soundboard/rename', { id: s.id, name, ...(emoji ? { emoji } : {}) }); toast(t('board.updated')); await refreshState(); }
      catch (e) { handleError(e); return false; }
      return true;
    },
  });
  const remove = (s) => confirmDialog(t('board.delTitle'), t('board.delText', { name: s.name }), t('common.delete') + ' 🗑', async (b) => {
    await run(b, async () => { await post('/api/soundboard/remove', { id: s.id }); toast(t('board.deleted')); await refreshState(); });
  });

  const tile = (s, canEdit, canDelete) => {
    const main = h('button', { type: 'button', class: 'tile-main', title: t('board.playIn'), onclick: (e) => play(s, e.currentTarget.closest('.tile')) },
      h('span', { class: 'tile-emoji', 'aria-hidden': 'true' }, s.emoji || '🔊'),
      h('span', { class: 'tile-name' }, s.name), h('small', null, fmtDur(s.durationMs)));
    const ib = (txt, label, fn, cls = '', extra) => h('button', { type: 'button', class: 'tile-ib ' + cls, 'aria-label': label, title: label, onclick: (e) => fn(e.currentTarget), ...extra }, txt);
    const on = preview.key() === 'b' + s.id;
    return h('div', { class: 'tile' + (s.fav ? ' fav' : '') },
      main,
      h('div', { class: 'tile-tools' },
        ib(on ? '⏸' : '🎧', t('board.preview', { name: s.name }), () => preview.toggle('b' + s.id, '/api/soundboard/audio?id=' + encodeURIComponent(s.id), () => toast(t('board.noPreview'), 'err')), 'prev'),
        ib(s.fav ? '★' : '☆', s.fav ? t('board.unfav') : t('board.fav'), (b) => toggleFav(s, b), s.fav ? 'on' : ''),
        canEdit ? ib('✏️', t('board.rename', { name: s.name }), () => rename(s)) : null,
        canDelete ? ib('🗑', t('board.delete', { name: s.name }), () => remove(s), 'del') : null));
  };

  function draw() {
    const s = store.state;
    if (!s) return;
    const admin = s.me.isAdmin;
    const byName = (a, b) => a.name.localeCompare(b.name, locale());
    const order = {
      name: byName,
      short: (a, b) => (a.durationMs - b.durationMs) || byName(a, b),
      long: (a, b) => (b.durationMs - a.durationMs) || byName(a, b),
    }[sort] || byName;
    const all = [...s.sounds].sort(order);
    const list = all.filter((x) => (filter === 'fav' ? x.fav : filter === 'mine' ? x.own : true)
      && (!query || x.name.toLowerCase().includes(query)));
    count.textContent = t('board.count', { shown: list.length, total: all.length });
    region(grid, JSON.stringify([list, admin, filter, query, sort, preview.key(), t('board.fAll')]), () => {
      if (!all.length) return empty('🔇', t('board.empty'));
      if (!list.length) return empty('🔎', t('board.noMatch'));
      const tiles = (xs) => h('div', { class: 'tiles' }, xs.map((x) => tile(x, x.own || admin, admin)));
      // Without search or filter: favourites as their own row, then everything else.
      if (filter === 'all' && !query) {
        const favs = list.filter((x) => x.fav), rest = list.filter((x) => !x.fav);
        return [favs.length ? [h('h2', { class: 'section-title' }, '★ ' + t('board.fFav')), tiles(favs)] : null,
          favs.length && rest.length ? h('h2', { class: 'section-title' }, t('board.others')) : null, tiles(rest)];
      }
      return tiles(list);
    });
  }

  const unsub = preview.subscribe(draw);
  function update() {
    const s = store.state;
    if (!s) return;
    const on = s.modules.soundboard;
    region(off, on ? 'on' : 'off', () => on ? null : notice('🔇', t('board.offTitle'), t('board.offText')));
    body.hidden = !on;
    if (!on) return;
    if (Date.now() - volTouched > 3000 && document.activeElement !== vol) { vol.value = s.soundboardVolume; volOut.textContent = s.soundboardVolume + '%'; }
    draw();
  }
  return { update, destroy() { unsub(); preview.stop(); sendVol.cancel(); search.cancel(); } };
}
