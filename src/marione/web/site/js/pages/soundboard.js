import { h, region, fmtDur, debounce, fileBase, checkAudio } from '../util.js';
import { store } from '../store.js';
import { api, post } from '../api.js';
import { run, refreshState, handleError } from '../data.js';
import { toast } from '../toast.js';
import { card, pageHead, notice, btn, nameModal, confirmDialog, pickFile } from '../ui.js';

let audio = null, playingId = null;
function stopPreview() { if (audio) { audio.pause(); audio = null; } playingId = null; }

/** Apre la modale di caricamento per un file (usata anche dal drag&drop globale). */
export function openAdd(file) {
  const err = checkAudio(file);
  if (err) { toast(err, 'err'); return; }
  nameModal({
    title: 'Nuovo suono', file, name: fileBase(file.name), withEmoji: true, okLabel: 'Aggiungi 🔊',
    onSubmit: async ({ name, emoji }) => {
      const fd = new FormData();
      fd.append('name', name);
      if (emoji) fd.append('emoji', emoji);
      fd.append('file', file);
      try {
        await api('/api/soundboard/add', { method: 'POST', form: fd });
        toast(`«${name}» aggiunto alla soundboard!`);
        await refreshState();
      } catch (e) { handleError(e); return false; }
      return true;
    },
  });
}

export function mount(root) {
  root.append(pageHead('Soundboard', 'Premi un tasto e fai ridere (o piangere) la vocale.'));
  const off = h('div'), body = h('div', { class: 'stack-lg' });
  root.append(off, body);

  // ---- controlli ----
  const volOut = h('output', { class: 'vol-out' }, '80%');
  const vol = h('input', { type: 'range', min: '0', max: '100', step: '1', value: '80', 'aria-label': 'Volume' });
  let volTouched = 0;
  const sendVol = debounce(async () => {
    try { await post('/api/soundboard/volume', { percent: Number(vol.value) }); } catch (e) { handleError(e); }
  }, 350);
  vol.addEventListener('input', () => { volOut.textContent = vol.value + '%'; volTouched = Date.now(); sendVol(); });
  const stopBtn = btn('⏹ Ferma tutto', 'danger', { onclick: () => run(stopBtn, () => post('/api/soundboard/stop')) });
  const controls = card('controls', h('label', { class: 'vol' }, h('span', { class: 'field-label' }, '🔈 Volume'), vol, volOut), stopBtn);
  const grid = h('div', { class: 'tiles' });
  body.append(controls, grid);

  const play = async (s, tile) => {
    tile.classList.remove('pulse'); void tile.offsetWidth; tile.classList.add('pulse');
    try { await post('/api/soundboard/play', { id: s.id }); }
    catch (e) { handleError(e, { not_in_voice: 'Entra prima in un canale vocale 🎧' }); }
  };

  const preview = (s, b) => {
    if (playingId === s.id) { stopPreview(); syncPreview(); return; }
    stopPreview();
    audio = new Audio('/api/soundboard/audio?id=' + encodeURIComponent(s.id));
    playingId = s.id;
    audio.addEventListener('ended', () => { stopPreview(); syncPreview(); });
    audio.addEventListener('error', () => { stopPreview(); syncPreview(); toast('Anteprima non disponibile.', 'err'); });
    audio.play().catch(() => {});
    syncPreview();
  };
  const syncPreview = () => grid.querySelectorAll('[data-prev]').forEach((b) => {
    const on = b.dataset.prev === playingId;
    b.textContent = on ? '⏸' : '▶︎';
    b.setAttribute('aria-label', (on ? 'Ferma anteprima di ' : 'Anteprima di ') + b.dataset.name);
  });

  const toggleFav = (s, b) => run(b, async () => { await post('/api/soundboard/favorite', { id: s.id }); await refreshState(); });
  const rename = (s) => nameModal({
    title: 'Modifica suono', name: s.name, emoji: s.emoji, withEmoji: true, okLabel: 'Salva',
    onSubmit: async ({ name, emoji }) => {
      try { await post('/api/soundboard/rename', { id: s.id, name, ...(emoji ? { emoji } : {}) }); toast('Suono aggiornato.'); await refreshState(); }
      catch (e) { handleError(e); return false; }
      return true;
    },
  });
  const remove = (s) => confirmDialog('Eliminare il suono?', `«${s.name}» sparirà per tutti, per sempre.`, 'Elimina 🗑', async (b) => {
    await run(b, async () => { await post('/api/soundboard/remove', { id: s.id }); toast('Suono eliminato.'); await refreshState(); });
  });

  const tile = (s, canEdit) => {
    const main = h('button', { type: 'button', class: 'tile-main', onclick: (e) => play(s, e.currentTarget.closest('.tile')) },
      h('span', { class: 'tile-emoji', 'aria-hidden': 'true' }, s.emoji || '🔊'),
      h('span', { class: 'tile-name' }, s.name), h('small', null, fmtDur(s.durationMs)));
    const ib = (txt, label, fn, cls = '', extra) => h('button', { type: 'button', class: 'tile-ib ' + cls, 'aria-label': label, title: label, onclick: (e) => fn(e.currentTarget), ...extra }, txt);
    return h('div', { class: 'tile' + (s.fav ? ' fav' : '') },
      main,
      h('div', { class: 'tile-tools' },
        ib(playingId === s.id ? '⏸' : '▶︎', 'Anteprima di ' + s.name, (b) => preview(s, b), '', { 'data-prev': s.id, 'data-name': s.name }),
        ib(s.fav ? '★' : '☆', s.fav ? 'Togli dai preferiti' : 'Aggiungi ai preferiti', (b) => toggleFav(s, b), s.fav ? 'on' : ''),
        canEdit ? ib('✏️', 'Rinomina ' + s.name, () => rename(s)) : null,
        canEdit ? ib('🗑', 'Elimina ' + s.name, () => remove(s), 'del') : null));
  };

  const addTile = h('button', { type: 'button', class: 'tile-add', onclick: () => pickFile(openAdd) },
    h('span', { class: 'plus' }, '＋'), h('strong', null, 'Aggiungi un suono'), h('small', null, 'Clicca o trascina qui un file audio (max 8 MB)'));

  function update() {
    const s = store.state;
    if (!s) return;
    const on = s.modules.soundboard;
    region(off, on ? 'on' : 'off', () => on ? null : notice('🔇', 'Soundboard spenta', 'La soundboard è in pausa. Chiedi a un amministratore di riaccenderla.'));
    body.hidden = !on;
    if (!on) return;
    if (Date.now() - volTouched > 3000 && document.activeElement !== vol) { vol.value = s.soundboardVolume; volOut.textContent = s.soundboardVolume + '%'; }
    const list = [...s.sounds].sort((a, b) => (b.fav - a.fav) || a.name.localeCompare(b.name, 'it'));
    region(grid, JSON.stringify([list, s.me.isAdmin]), () => [list.map((x) => tile(x, x.own || s.me.isAdmin)), addTile]);
  }
  return { update, destroy() { stopPreview(); sendVol.cancel(); } };
}
