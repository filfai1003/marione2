// Entrance sounds (administrators only): pick a member on the left, manage their sounds on the right.
import { fill, h, fmtDur, fmtKB, fileBase, checkAudio, avatar } from '../util.js';
import { store } from '../store.js';
import { api, post } from '../api.js';
import { run, handleError } from '../data.js';
import { toast } from '../toast.js';
import { t } from '../i18n.js';
import { card, cardTitle, pageHead, notice, btn, nameModal, confirmDialog, pickFile, searchBox, empty, preview } from '../ui.js';

export function mount(root) {
  root.append(pageHead(t('ent.title'), t('ent.sub')));
  const off = h('div');
  const layout = h('div', { class: 'split' });
  root.append(off, layout);
  let members = [], limit = 10, query = '', selected = null, sounds = null;

  // ---- left: members ----
  const search = searchBox(t('ent.searchMember'), (q) => { query = q.toLowerCase(); drawMembers(); }, 120);
  const memberList = h('ul', { class: 'pick-list', role: 'listbox', 'aria-label': t('ent.members') });
  const left = card('split-left', cardTitle('👥', t('ent.members')), search.el, memberList);

  // ---- right: the selected member's sounds ----
  const right = card('split-right');
  layout.append(left, right);

  function drawMembers() {
    const list = members.filter((m) => !query || m.name.toLowerCase().includes(query));
    fill(memberList, ...(list.length ? list.map((m) => h('li', null,
      h('button', { type: 'button', class: 'pick' + (selected && selected.id === m.id ? ' on' : ''), role: 'option',
        'aria-selected': String(!!(selected && selected.id === m.id)), onclick: () => select(m) },
      avatar(m, 34), h('span', { class: 'pick-name' }, m.name),
      h('span', { class: 'tag counter' + (m.count ? '' : ' zero') }, String(m.count)))))
      : [h('li', null, empty('🔎', t('ent.noMember')))]));
  }

  function drawSounds() {
    layout.classList.toggle('has-selection', !!selected);
    if (!selected) {
      fill(right, empty('👈', t('ent.pick')));
      return;
    }
    const n = sounds ? sounds.length : 0, full = n >= limit;
    const back = btn('‹ ' + t('ent.back'), 'ghost sm back-btn', { onclick: () => { selected = null; drawMembers(); drawSounds(); } });
    const upload = btn('＋ ' + t('ent.upload'), 'primary sm', { disabled: full, onclick: () => pickFile(openAdd) });
    fill(right, 
      back,
      cardTitle('🎺', selected.name, h('span', { class: 'tag counter' }, `${n}/${limit}`)),
      h('p', { class: 'muted small' }, t('ent.explain')),
      sounds === null ? h('p', { class: 'muted center' }, t('common.loading'))
        : n ? h('ul', { class: 'ents' }, sounds.map(row)) : empty('🎶', t('ent.none')),
      h('div', { class: 'row-end' }, full ? h('span', { class: 'hint' }, t('ent.full')) : h('span', { class: 'hint' }, t('ent.hint')), upload));
  }

  const row = (e) => {
    const key = 'e' + selected.id + ':' + e.name;
    const on = preview.key() === key;
    return h('li', { class: 'ent' },
      h('button', { type: 'button', class: 'round-play', 'aria-label': t('board.preview', { name: e.name }),
        onclick: () => preview.toggle(key, `/api/entrance/audio?memberId=${encodeURIComponent(selected.id)}&name=${encodeURIComponent(e.name)}`, () => toast(t('board.noPreview'), 'err')) }, on ? '⏸' : '▶︎'),
      h('span', { class: 'ent-main' }, h('strong', null, e.name), h('small', null, fmtKB(e.size) + ' · ' + fmtDur(e.durationMs))),
      h('button', { type: 'button', class: 'icon-btn del', 'aria-label': t('board.delete', { name: e.name }), title: t('common.delete'), onclick: () => del(e) }, '🗑'));
  };

  const del = (e) => confirmDialog(t('ent.delTitle'), t('ent.delText', { name: e.name, member: selected.name }), t('common.delete') + ' 🗑', async (b) => {
    await run(b, async () => {
      await post('/api/entrance/remove', { memberId: selected.id, name: e.name });
      toast(t('board.deleted'));
      await reload();
    });
  });

  function openAdd(file) {
    if (!selected) { toast(t('ent.pickFirst'), 'err'); return; }
    if (sounds && sounds.length >= limit) { toast(t('ent.full'), 'err'); return; }
    const err = checkAudio(file);
    if (err) { toast(err, 'err'); return; }
    const who = selected;
    nameModal({
      title: t('ent.newFor', { name: who.name }), file, name: fileBase(file.name), withEmoji: false, okLabel: t('ent.upload') + ' 🎺',
      onSubmit: async ({ name }) => {
        const fd = new FormData();
        fd.append('memberId', who.id);
        fd.append('name', name);
        fd.append('file', file);
        try { await api('/api/entrance/add', { method: 'POST', form: fd }); toast(t('ent.added', { name, member: who.name })); await reload(); }
        catch (e) { handleError(e); return false; }
        return true;
      },
    });
  }

  async function select(m) {
    selected = m; sounds = null;
    drawMembers(); drawSounds();
    try {
      const r = await api('/api/entrance/list?memberId=' + encodeURIComponent(m.id));
      if (selected !== m) return;
      sounds = r.entrances; limit = r.limit;
      drawSounds();
    } catch (e) { handleError(e); }
  }

  async function reload() {
    try {
      const r = await api('/api/entrance/members');
      members = r.members; limit = r.limit;
      if (selected) { selected = members.find((m) => m.id === selected.id) || selected; }
      drawMembers();
      if (selected) await select(selected);
    } catch (e) { handleError(e); }
  }

  const unsub = preview.subscribe(() => { if (selected && sounds) drawSounds(); });
  drawSounds();
  reload();

  function update() {
    const s = store.state;
    if (!s) return;
    const on = s.modules.sound;
    fill(off, on ? '' : notice('🔕', t('ent.offTitle'), t('ent.offText')));
  }
  return { update, drop: openAdd, destroy() { unsub(); preview.stop(); search.cancel(); } };
}
