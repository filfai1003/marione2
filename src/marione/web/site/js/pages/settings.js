// Settings (administrators only), grouped into collapsible sections.
import { fill, h, region, fmt } from '../util.js';
import { store, set } from '../store.js';
import { api, post } from '../api.js';
import { run, refreshState, handleError, setBalance } from '../data.js';
import { toast } from '../toast.js';
import { t, LANGS, LANG_NAMES, locale } from '../i18n.js';
import { pageHead, field, btn, fillSelect, progress, collapsible, fieldError, searchBox, empty } from '../ui.js';

const SUGGESTED = ['anthropic/claude-haiku-4.5', 'anthropic/claude-sonnet-4.5', 'openai/gpt-5-mini', 'openai/gpt-5-nano',
  'google/gemini-2.5-flash', 'google/gemini-2.5-flash-lite', 'deepseek/deepseek-chat-v3.1', 'mistralai/mistral-small-3.2-24b-instruct'];
const MODS = [
  ['economy', '💰'], ['sound', '🎺'], ['soundboard', '🔊'], ['roles', '🎖️', true], ['rob', '🦹'], ['agent', '🤖'],
];

export function mount(root) {
  root.append(pageHead(t('set.title'), t('set.sub')));
  const usd = new Intl.NumberFormat(locale(), { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 });
  const mods = h('ul', { class: 'mods' });
  const sections = h('div', { class: 'stack' });
  root.append(sections);

  // ---- features ----
  const toggle = (key, name, on) => {
    const sw = h('button', { type: 'button', class: 'switch', role: 'switch', 'aria-checked': String(on), 'aria-label': name });
    sw.addEventListener('click', () => run(sw, async () => {
      const r = await post('/api/admin/feature', { key, on: !on });
      set({ state: { ...store.state, modules: r.modules } });
      toast(t(r.modules[key] ? 'set.turnedOn' : 'set.turnedOff', { name }));
      await refreshState();
    }));
    return sw;
  };
  const drawMods = (m) => fill(mods, ...MODS.map(([k, emoji, warn]) => h('li', null,
    h('span', { class: 'mod-emoji', 'aria-hidden': 'true' }, emoji),
    h('span', { class: 'mod-main' }, h('strong', null, t('mod.' + k)), h('small', null, t('mod.' + k + 'Desc')),
      warn ? h('small', { class: 'warn' }, '⚠ ' + t('mod.rolesWarn')) : null),
    toggle(k, t('mod.' + k), !!m[k]))));

  // ---- balances ----
  const sel = h('select', { required: true, 'aria-label': t('set.member') });
  const amt = h('input', { type: 'number', min: '0', step: '1', inputmode: 'numeric', placeholder: t('eco.amountPh') });
  const err = fieldError();
  let action = 'give';
  const seg = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': t('set.action') },
    [['give', t('set.give')], ['take', t('set.take')], ['set', t('set.set')]].map(([v, l]) => {
      const b = h('button', { type: 'button', class: 'seg-b' + (v === action ? ' on' : ''), role: 'radio', 'aria-checked': String(v === action), onclick: () => {
        action = v;
        seg.querySelectorAll('.seg-b').forEach((x) => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-checked', String(on)); });
      } }, l);
      return b;
    }));
  const go = btn(t('set.apply') + ' ✓', 'primary block', { type: 'submit' });
  const balForm = h('form', { class: 'stack narrow-form', novalidate: true, onsubmit: (e) => {
    e.preventDefault();
    const amount = Math.floor(Number(amt.value));
    if (!sel.value) { err.show(t('eco.errPickMember')); sel.focus(); return; }
    if (!(amount >= 0) || amt.value === '') { err.show(t('eco.errAmount')); amt.focus(); return; }
    err.show('');
    run(go, async () => {
      const r = await post('/api/admin/balance', { memberId: sel.value, action, amount });
      toast(t('set.newBalance', { amount: fmt(r.balance) }));
      if (sel.value === store.me.id) setBalance(r.balance);
      amt.value = '';
      await refreshState();
    });
  } }, field(t('set.member'), sel), seg, field(t('eco.amount'), amt, null, err.el), go);

  // ---- AI: models + costs ----
  const aiBox = h('div', { class: 'stack' });
  const usageBox = h('div', { class: 'stack' });
  let ai = null;
  const price = (m) => `$${m.promptPerMillion} / $${m.completionPerMillion} · ${fmt(Math.round(m.context / 1000))}k`;
  function modelPicker(kind, current, def) {
    const box = h('div', { class: 'model-pick' });
    const title = kind === 'model' ? t('ai.main') : t('ai.gate');
    const hint = kind === 'model' ? t('ai.mainHint') : t('ai.gateHint');
    const cur = h('div', { class: 'model-cur' }, h('span', { class: 'mono' }, current),
      current === def ? h('span', { class: 'tag' }, t('ai.default')) : btn(t('ai.reset'), 'ghost sm', { onclick: (e) => save(kind, null, e.currentTarget) }));
    let list;
    if (ai.models.length) {
      const results = h('ul', { class: 'model-list', role: 'listbox', 'aria-label': title });
      const draw = (q) => {
        const qq = q.toLowerCase();
        // Empty search: the current model and a few well-known good picks; otherwise matches.
        const found = (qq ? ai.models.filter((m) => m.id.toLowerCase().includes(qq) || m.name.toLowerCase().includes(qq))
          : ai.models.filter((m) => m.id === current || SUGGESTED.includes(m.id))).slice(0, 8);
        fill(results, ...(found.length ? found.map((m) => h('li', null,
          h('button', { type: 'button', class: 'pick' + (m.id === current ? ' on' : ''), role: 'option', 'aria-selected': String(m.id === current),
            onclick: (e) => save(kind, m.id, e.currentTarget) },
          h('span', { class: 'pick-name' }, m.name, h('small', { class: 'mono' }, m.id)), h('small', { class: 'price' }, price(m))))) : [h('li', null, empty('🔎', t('ai.noModel')))]));
      };
      const s = searchBox(t('ai.search'), draw, 100);
      draw('');
      list = h('div', { class: 'stack' }, s.el, results, h('p', { class: 'hint' }, t('ai.priceHint')));
    } else {
      const input = h('input', { type: 'text', value: current, placeholder: 'vendor/model', 'aria-label': title });
      list = h('div', { class: 'inline-form' }, input, btn(t('common.save'), 'primary sm', { onclick: (e) => save(kind, input.value.trim(), e.currentTarget) }));
    }
    box.append(h('h3', { class: 'section-title' }, title), h('p', { class: 'hint' }, hint), cur, list);
    return box;
  }
  async function save(kind, value, b) {
    await run(b, async () => {
      ai = await post('/api/admin/ai', { [kind === 'model' ? 'model' : 'gateModel']: value });
      toast(t('ai.saved'));
      drawAi();
    });
  }
  function drawAi() {
    if (!ai) { fill(aiBox, h('p', { class: 'muted' }, t('common.loading'))); return; }
    fill(aiBox, 
      ai.aiEnabled ? null : h('p', { class: 'warn-box' }, '⚠ ' + t('ai.off')),
      h('div', { class: 'grid g-2' }, modelPicker('model', ai.model, ai.defaultModel), modelPicker('gate', ai.gateModel, ai.defaultGateModel)));
  }
  async function loadAi() {
    try { ai = await api('/api/admin/ai'); drawAi(); } catch (e) { handleError(e); }
    let u;
    try { u = await api('/api/admin/usage'); } catch (e) { handleError(e); return; }
    const bar = (label, v, max) => {
      const pct = max > 0 ? (v / max) * 100 : 0;
      return h('div', { class: 'usage-row' }, h('div', { class: 'usage-top' }, h('span', null, label),
        h('strong', null, usd.format(v) + ' / ' + usd.format(max))), progress(pct, label, pct >= 90 ? 'hot' : ''));
    };
    fill(usageBox, h('h3', { class: 'section-title' }, '💸 ' + t('ai.costs')),
      bar(t('ai.today'), u.todayUsd, u.dailyBudgetUsd), bar(t('ai.month'), u.monthUsd, u.monthlyBudgetUsd),
      u.byModel.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'lb usage' },
        h('thead', null, h('tr', null, h('th', { scope: 'col' }, t('ai.model')), h('th', { scope: 'col', class: 'c-bal' }, t('ai.calls')), h('th', { scope: 'col', class: 'c-bal' }, t('ai.cost')))),
        h('tbody', null, u.byModel.map((m) => h('tr', null, h('td', { class: 'mono' }, m.model), h('td', { class: 'c-bal' }, fmt(m.calls)), h('td', { class: 'c-bal' }, usd.format(m.costUsd)))))))
        : h('p', { class: 'muted' }, t('ai.noCalls')));
  }

  // ---- server language ----
  const langSel = h('select', { 'aria-label': t('set.serverLang') }, LANGS.map((l) => h('option', { value: l }, LANG_NAMES[l])));
  const langBtn = btn(t('common.save'), 'primary sm', { onclick: () => run(langBtn, async () => {
    const r = await post('/api/admin/settings', { serverLanguage: langSel.value });
    langSel.value = r.serverLanguage;
    toast(t('set.serverLangSaved', { name: LANG_NAMES[r.serverLanguage] }));
  }) });
  api('/api/admin/settings').then((r) => { langSel.value = r.serverLanguage; }).catch(handleError);

  sections.append(
    collapsible('🎛️', t('set.features'), t('set.featuresSub'), mods, true),
    collapsible('🧾', t('set.balances'), t('set.balancesSub'), balForm),
    collapsible('🤖', t('set.ai'), t('set.aiSub'), h('div', { class: 'stack-lg' }, aiBox, usageBox)),
    collapsible('🌍', t('set.language'), t('set.languageSub'), h('div', { class: 'stack' },
      h('p', { class: 'hint' }, t('set.serverLangHint')), h('div', { class: 'inline-form' }, langSel, langBtn))));
  sections.querySelector('details:nth-child(3)').addEventListener('toggle', (e) => { if (e.target.open && !ai) loadAi(); });
  drawAi();

  function update() {
    const s = store.state;
    if (!s) return;
    region(mods, JSON.stringify([s.modules, t('mod.economy')]), () => { drawMods(s.modules); return []; });
    const all = [{ id: store.me.id, name: store.me.name + ' (' + t('common.you') + ')' }, ...s.members];
    fillSelect(sel, all, t('eco.pickMember'));
  }
  return { update };
}
