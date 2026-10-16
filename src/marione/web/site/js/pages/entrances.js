import { h, region, fmtDur, fmtKB, fileBase, checkAudio } from '../util.js';
import { store } from '../store.js';
import { api, post } from '../api.js';
import { run, refreshState, handleError } from '../data.js';
import { toast } from '../toast.js';
import { card, cardTitle, pageHead, notice, btn, nameModal, confirmDialog, pickFile } from '../ui.js';

let audio = null, playing = null;
const stop = () => { if (audio) audio.pause(); audio = null; playing = null; };

export function openAdd(file) {
  const s = store.state;
  if (s && s.entrances.length >= s.entranceLimit) { toast(`Hai già ${s.entranceLimit} suoni d'entrata: eliminane uno.`, 'err'); return; }
  const err = checkAudio(file);
  if (err) { toast(err, 'err'); return; }
  nameModal({
    title: "Nuovo suono d'entrata", file, name: fileBase(file.name), withEmoji: false, okLabel: 'Carica 🎺',
    onSubmit: async ({ name }) => {
      const fd = new FormData();
      fd.append('name', name);
      fd.append('file', file);
      try { await api('/api/entrance/add', { method: 'POST', form: fd }); toast(`«${name}» è il tuo nuovo suono d'entrata!`); await refreshState(); }
      catch (e) { handleError(e); return false; }
      return true;
    },
  });
}

export function mount(root) {
  root.append(pageHead("Suoni d'entrata", 'La tua sigla personale quando arrivi in vocale.'));
  const off = h('div'), body = h('div', { class: 'stack-lg' });
  const listBox = h('div'), dz = h('div');
  body.append(card('info', h('div', { class: 'info-row' }, h('span', { class: 'info-emoji mar-anim-bob', 'aria-hidden': 'true' }, '🎺'),
    h('p', null, 'Quando entri in vocale ', h('strong', null, 'Marione suona uno dei tuoi suoni a caso'), '. Più ne carichi, più è una sorpresa.'))), listBox, dz);
  root.append(off, body);

  const setBtn = (b, id) => { b.textContent = playing === id ? '⏸' : '▶︎'; };
  const prev = (e, b) => {
    const wasOn = playing === e.name;
    stop();
    document.querySelectorAll('[data-ent]').forEach((x) => { x.textContent = '▶︎'; });
    if (wasOn) return;
    audio = new Audio('/api/entrance/audio?name=' + encodeURIComponent(e.name));
    playing = e.name; setBtn(b, e.name);
    audio.addEventListener('ended', () => { stop(); b.textContent = '▶︎'; });
    audio.addEventListener('error', () => { stop(); b.textContent = '▶︎'; toast('Anteprima non disponibile.', 'err'); });
    audio.play().catch(() => {});
  };
  const del = (e) => confirmDialog('Eliminare il suono?', `«${e.name}» non verrà più suonato quando entri.`, 'Elimina 🗑', async (b) => {
    await run(b, async () => { await post('/api/entrance/remove', { name: e.name }); toast('Suono eliminato.'); await refreshState(); });
  });

  const row = (e) => h('li', { class: 'ent' },
    h('button', { type: 'button', class: 'round-play', 'data-ent': e.name, 'aria-label': 'Anteprima di ' + e.name, onclick: (ev) => prev(e, ev.currentTarget) }, playing === e.name ? '⏸' : '▶︎'),
    h('span', { class: 'ent-main' }, h('strong', null, e.name), h('small', null, fmtKB(e.size) + ' · ' + fmtDur(e.durationMs))),
    h('button', { type: 'button', class: 'icon-btn del', 'aria-label': 'Elimina ' + e.name, title: 'Elimina', onclick: () => del(e) }, '🗑'));

  function update() {
    const s = store.state;
    if (!s) return;
    const on = s.modules.sound;
    region(off, on ? 'on' : 'off', () => on ? null : notice('🔕', "Suoni d'entrata spenti", "Questa funzione è in pausa. Chiedi a un amministratore di riaccenderla."));
    body.hidden = !on;
    if (!on) return;
    const n = s.entrances.length, lim = s.entranceLimit, full = n >= lim;
    region(listBox, JSON.stringify(s.entrances), () => card('', cardTitle('🎶', 'I tuoi suoni', h('span', { class: 'tag counter' }, `${n}/${lim}`)),
      n ? h('ul', { class: 'ents' }, s.entrances.map(row)) : h('p', { class: 'muted empty' }, 'Nessun suono ancora: carica il primo e fai il tuo ingresso trionfale.')));
    region(dz, full ? 'full' : 'open', () => h('button', { type: 'button', class: 'tile-add wide', disabled: full, onclick: () => pickFile(openAdd) },
      h('span', { class: 'plus' }, '＋'), h('strong', null, full ? 'Limite raggiunto' : 'Carica un suono'),
      h('small', null, full ? 'Elimina un suono per farne spazio.' : 'Clicca o trascina qui un file audio (max 8 MB, 15 secondi)')));
  }
  return { update, destroy: stop };
}
