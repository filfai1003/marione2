// "Marione's brain" (administrators only): the system prompts and what the AI remembers.
import { fill, h, ago, avatar, fmt } from '../util.js';
import { api, post } from '../api.js';
import { run, handleError } from '../data.js';
import { toast } from '../toast.js';
import { t } from '../i18n.js';
import { card, cardTitle, pageHead, btn, tabs, pager, searchBox, empty, confirmDialog } from '../ui.js';

const MEMBERS_PAGE = 20, LINES_PAGE = 20, CHANNEL_PAGE = 30;
const CATEGORIES = ['identity', 'likes', 'dislikes', 'opinions', 'personality', 'humor', 'relationship', 'notes'];

export function mount(root, sub) {
  root.append(pageHead(t('brain.title'), t('brain.sub')),
    h('p', { class: 'privacy' }, '🔒 ', t('brain.privacy')));
  const panel = h('div', { class: 'tab-panel', role: 'tabpanel' });
  let tab = ['prompt', 'members', 'channels'].includes(sub) ? sub : 'members';
  const bar = tabs([['members', '👥', t('brain.tabMembers')], ['channels', '💬', t('brain.tabChannels')], ['prompt', '📜', t('brain.tabPrompt')]],
    tab, (k) => show(k, true));
  root.append(bar.el, panel);

  // ---------------- members ----------------
  const ms = { q: '', offset: 0, total: 0, items: [], seq: 0, open: null };
  const mSearch = searchBox(t('brain.searchMember'), (q) => { ms.q = q; loadMembers(0); });
  const mList = h('div', { class: 'stack' });
  const detail = h('div');
  const membersView = h('div', { class: 'split' },
    card('split-left', cardTitle('👥', t('brain.tabMembers')), mSearch.el, mList), card('split-right', detail));

  async function loadMembers(offset) {
    const id = ++ms.seq;
    try {
      const r = await api(`/api/admin/memory/members?offset=${offset}&limit=${MEMBERS_PAGE}&q=${encodeURIComponent(ms.q)}`);
      if (id !== ms.seq) return;
      Object.assign(ms, { offset, total: r.total, items: r.items });
      drawMembers();
    } catch (e) { handleError(e); }
  }
  function drawMembers() {
    fill(mList, 
      ms.items.length ? h('ul', { class: 'pick-list' }, ms.items.map((m) => h('li', null,
        h('button', { type: 'button', class: 'pick' + (ms.open === m.id ? ' on' : ''), onclick: () => openMember(m.id) },
          avatar(m, 34), h('span', { class: 'pick-name' }, m.name,
            h('small', null, t('brain.counts', { facts: m.facts, episodes: m.episodes, messages: m.messages })))))))
        : empty('🫙', ms.q ? t('brain.noMatch') : t('brain.nothing')),
      pager(ms.total, ms.offset, MEMBERS_PAGE, loadMembers));
  }

  async function openMember(id, offset = 0) {
    ms.open = id;
    membersView.classList.add('has-selection');
    drawMembers();
    let r;
    try { r = await api(`/api/admin/memory/member?memberId=${encodeURIComponent(id)}&offset=${offset}&limit=${LINES_PAGE}`); }
    catch (e) { handleError(e); return; }
    if (ms.open !== id) return;
    const back = btn('‹ ' + t('ent.back'), 'ghost sm back-btn', { onclick: () => { ms.open = null; membersView.classList.remove('has-selection'); fill(detail, empty('👈', t('brain.pick'))); drawMembers(); } });
    const forget = btn('🧽 ' + t('brain.forget'), 'danger sm', { onclick: () => confirmDialog(t('brain.forgetTitle'), t('brain.forgetText', { name: r.member.name }), t('brain.forget'), async (b) => {
      await run(b, async () => {
        const x = await post('/api/admin/memory/forget', { memberId: id });
        toast(t('brain.forgotten', { count: x.removed }));
        ms.open = null;
        fill(detail, empty('🧽', t('brain.pick')));
        membersView.classList.remove('has-selection');
        await loadMembers(0);
      });
    }) });
    const byCat = CATEGORIES.map((c) => [c, r.facts.filter((f) => f.category === c)]).filter(([, fs]) => fs.length);
    const dots = (n) => h('span', { class: 'dots', title: t('brain.confidence', { n }), 'aria-label': t('brain.confidence', { n }) },
      [1, 2, 3, 4, 5].map((i) => h('span', { class: i <= n ? 'on' : '' })));
    const delFact = (f) => confirmDialog(t('brain.delFactTitle'), '«' + f.text + '»', t('common.delete') + ' 🗑', async (b) => {
      await run(b, async () => { await post('/api/admin/memory/fact/delete', { id: f.id }); toast(t('board.deleted')); await openMember(id); await loadMembers(ms.offset); });
    });
    fill(detail, 
      back,
      h('div', { class: 'member-head' }, avatar(r.member, 48), h('h2', null, r.member.name), h('span', { class: 'spacer' }), forget),
      h('h3', { class: 'section-title' }, '🗒️ ' + t('brain.facts')),
      byCat.length ? h('div', { class: 'facts' }, byCat.map(([c, fs]) => h('div', { class: 'fact-group' },
        h('span', { class: 'eyebrow' }, t('brain.cat.' + c)),
        h('ul', { class: 'fact-list' }, fs.map((f) => h('li', null,
          h('span', { class: 'fact-text' }, f.text), dots(f.confidence),
          h('button', { type: 'button', class: 'icon-btn del', 'aria-label': t('common.delete'), title: t('common.delete'), onclick: () => delFact(f) }, '🗑')))))))
        : empty('🫙', t('brain.noFacts')),
      h('h3', { class: 'section-title' }, '📈 ' + t('brain.habits')),
      r.habits && r.habits.length ? h('ul', { class: 'habits' }, r.habits.map((line) => h('li', null, line))) : empty('🫙', t('brain.noHabits')),
      h('h3', { class: 'section-title' }, '🎞️ ' + t('brain.episodes')),
      r.episodes.length ? h('ul', { class: 'quotes' }, r.episodes.map((e) => h('li', null, h('p', null, e.text), h('small', null, ago(e.at)))))
        : empty('🫙', t('brain.noEpisodes')),
      h('h3', { class: 'section-title' }, '💬 ' + t('brain.messages', { count: fmt(r.messages.total) })),
      r.messages.items.length ? h('ul', { class: 'log' }, r.messages.items.map((m) => h('li', null,
        h('small', null, m.channel + ' · ' + ago(m.at)), h('p', null, m.text)))) : empty('🫙', t('brain.noMessages')),
      pager(r.messages.total, offset, LINES_PAGE, (o) => openMember(id, o)));
  }

  // ---------------- channels ----------------
  const channelsView = h('div', { class: 'split' });
  const chList = h('div', { class: 'stack' }), chDetail = h('div');
  channelsView.append(card('split-left', cardTitle('💬', t('brain.tabChannels')), chList), card('split-right', chDetail));
  let openChannel = null;
  async function loadChannels() {
    try {
      const r = await api('/api/admin/memory/channels');
      fill(chList, r.items.length ? h('ul', { class: 'pick-list' }, r.items.map((c) => h('li', null,
        h('button', { type: 'button', class: 'pick' + (openChannel === c.id ? ' on' : ''), onclick: () => showChannel(c) },
          h('span', { class: 'pick-name' }, c.name, h('small', null, t('brain.lines', { count: fmt(c.messages) }) + (c.updatedAt ? ' · ' + ago(c.updatedAt) : ''))))))) : empty('🫙', t('brain.nothing')));
      if (!openChannel) fill(chDetail, empty('👈', t('brain.pickChannel')));
    } catch (e) { handleError(e); }
  }
  async function showChannel(c, offset = 0) {
    openChannel = c.id;
    channelsView.classList.add('has-selection');
    let r;
    try { r = await api(`/api/admin/memory/channel?channelId=${encodeURIComponent(c.id)}&offset=${offset}&limit=${CHANNEL_PAGE}`); }
    catch (e) { handleError(e); return; }
    const back = btn('‹ ' + t('ent.back'), 'ghost sm back-btn', { onclick: () => { openChannel = null; channelsView.classList.remove('has-selection'); loadChannels(); } });
    fill(chDetail, back,
      h('div', { class: 'member-head' }, h('h2', null, c.name)),
      h('h3', { class: 'section-title' }, '🧾 ' + t('brain.summary')),
      c.summary ? h('blockquote', { class: 'summary' }, c.summary) : empty('🫙', t('brain.noSummary')),
      h('h3', { class: 'section-title' }, '💬 ' + t('brain.saved')),
      r.items.length ? h('ul', { class: 'log' }, r.items.map((m) => h('li', { class: m.isBot ? 'bot' : '' },
        h('small', null, (m.isBot ? '🍝 ' : '') + m.author + ' · ' + ago(m.at)), h('p', null, m.text)))) : empty('🫙', t('brain.noMessages')),
      pager(r.total, offset, CHANNEL_PAGE, (o) => showChannel(c, o)));
    loadChannels();
  }

  // ---------------- prompt ----------------
  const promptView = h('div', { class: 'stack' });
  async function loadPrompt() {
    try {
      const r = await api('/api/admin/ai/prompt');
      fill(promptView, h('p', { class: 'muted' }, t('brain.promptIntro')),
        ...r.parts.map((p, i) => h('details', { class: 'card fold', open: i === 0 || null },
          h('summary', null, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, '📜'),
            h('span', { class: 'fold-title' }, h('h2', null, t('brain.prompt.' + p.key)), h('small', null, t('brain.chars', { count: fmt(p.text.length) }))),
            h('span', { class: 'fold-chev', 'aria-hidden': 'true' }, '▾')),
          h('div', { class: 'fold-body' },
            h('div', { class: 'row-end' }, btn('📋 ' + t('brain.copy'), 'ghost sm', { onclick: async () => {
              try { await navigator.clipboard.writeText(p.text); toast(t('brain.copied')); } catch { toast(t('common.unexpected'), 'err'); }
            } })),
            h('pre', { class: 'prompt' }, p.text)))));
    } catch (e) { handleError(e); }
  }

  function show(key, fromUser) {
    tab = key;
    bar.select(key);
    panel.setAttribute('aria-labelledby', 'tab-' + key);
    if (key === 'members') { fill(panel, membersView); if (!ms.open) fill(detail, empty('👈', t('brain.pick'))); loadMembers(ms.offset); }
    if (key === 'channels') { fill(panel, channelsView); loadChannels(); }
    if (key === 'prompt') { fill(panel, promptView); loadPrompt(); }
    if (fromUser) history.replaceState(null, '', '#/brain/' + key);
  }
  show(tab);
  return { update() {}, route(next) { if (next && next !== tab) show(next); }, destroy() { mSearch.cancel(); } };
}
