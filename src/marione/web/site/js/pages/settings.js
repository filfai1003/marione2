import { h, region, fmt, safeColor } from '../util.js';
import { store, set } from '../store.js';
import { api, post } from '../api.js';
import { run, refreshState, handleError, setBalance } from '../data.js';
import { toast } from '../toast.js';
import { card, cardTitle, pageHead, field, btn, fillSelect, progress } from '../ui.js';

const MODS = [
  ['economy', '💰', 'Economia', 'Marioncelli, pagamenti, classifica e premi per la chiacchiera.'],
  ['sound', '🎺', "Suoni d'entrata", 'Suona la sigla personale di chi entra in vocale.'],
  ['soundboard', '🔊', 'Soundboard', 'La libreria di suoni condivisa da suonare in vocale.'],
  ['roles', '🎖️', 'Ruoli ricchezza', 'Un ruolo colorato in base al saldo.', 'Crea e assegna ruoli sul server'],
  ['rob', '🦹', 'Furto', 'Permette di rubare Marioncelli agli altri (con rischio multa).'],
  ['agent', '🤖', 'Risposte AI in chat', 'Marione risponde quando lo chiamano nei canali di testo.'],
];

const usd = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 });

export function mount(root) {
  root.append(pageHead('Impostazioni', 'Solo per chi comanda in cucina.'));
  const mods = h('div'), balBox = h('div'), usageBox = h('div');
  root.append(h('div', { class: 'stack-lg' }, mods, h('div', { class: 'grid g-2' }, balBox, usageBox)));

  // ---- moduli ----
  const toggle = (key, label, on) => {
    const sw = h('button', { type: 'button', class: 'switch', role: 'switch', 'aria-checked': String(on), 'aria-label': label });
    sw.addEventListener('click', () => run(sw, async () => {
      const r = await post('/api/admin/feature', { key, on: !on });
      set({ state: { ...store.state, modules: r.modules } });
      toast(`${label}: ${r.modules[key] ? 'acceso' : 'spento'}.`);
      await refreshState();
    }));
    return sw;
  };
  const modsCard = (m) => card('', cardTitle('🎛️', 'Funzioni del bot'),
    h('ul', { class: 'mods' }, MODS.map(([k, emoji, label, desc, warn]) => h('li', null,
      h('span', { class: 'mod-emoji' }, emoji),
      h('span', { class: 'mod-main' }, h('strong', null, label), h('small', null, desc), warn ? h('small', { class: 'warn' }, '⚠ ' + warn) : null),
      toggle(k, label, !!m[k])))));

  // ---- saldo ----
  const sel = h('select', { required: true });
  const amt = h('input', { type: 'number', min: '0', step: '1', inputmode: 'numeric', placeholder: 'Importo' });
  const reason = h('input', { type: 'text', maxlength: '120', placeholder: 'Motivo (facoltativo)' });
  let action = 'give';
  const seg = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': 'Azione' },
    [['give', 'Regala'], ['take', 'Togli'], ['set', 'Imposta']].map(([v, l]) => {
      const b = h('button', { type: 'button', class: 'seg-b' + (v === action ? ' on' : ''), role: 'radio', 'aria-checked': String(v === action), onclick: () => {
        action = v;
        seg.querySelectorAll('.seg-b').forEach((x) => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-checked', String(on)); });
      } }, l);
      return b;
    }));
  const go = btn('Applica ✓', 'primary block', { type: 'submit' });
  const balForm = h('form', { class: 'stack', onsubmit: (e) => {
    e.preventDefault();
    const amount = Math.floor(Number(amt.value));
    if (!sel.value) { toast('Scegli un membro.', 'err'); return; }
    if (!(amount >= 0) || amt.value === '') { toast('Inserisci un importo valido.', 'err'); return; }
    run(go, async () => {
      const r = await post('/api/admin/balance', { memberId: sel.value, action, amount, reason: reason.value.trim() });
      toast(`Nuovo saldo: ${fmt(r.balance)} 🪙`);
      if (sel.value === store.me.id) setBalance(r.balance);
      amt.value = ''; reason.value = '';
      await refreshState();
    });
  } }, field('Membro', sel), seg, field('Importo', amt), field('Motivo', reason), go);
  balBox.append(card('', cardTitle('🧾', 'Gestisci saldo'), balForm));

  // ---- costi AI ----
  const usageBody = h('div', { class: 'stack' });
  const refresh = btn('↻', 'ghost sm', { 'aria-label': 'Aggiorna', title: 'Aggiorna', onclick: () => run(refresh, load) });
  usageBox.append(card('', cardTitle('🤖', 'Costi AI', refresh), usageBody));
  async function load() {
    let u;
    try { u = await api('/api/admin/usage'); } catch (e) { handleError(e); return; }
    if (!u.aiEnabled) { usageBody.replaceChildren(h('p', { class: 'muted empty' }, 'AI spenta (nessuna chiave OpenRouter).')); return; }
    const bar = (label, v, max) => {
      const pct = max > 0 ? (v / max) * 100 : 0;
      return h('div', { class: 'usage-row' }, h('div', { class: 'usage-top' }, h('span', null, label),
        h('strong', null, usd.format(v) + ' / ' + usd.format(max))), progress(pct, label, pct >= 90 ? 'hot' : ''));
    };
    usageBody.replaceChildren(bar('Oggi', u.todayUsd, u.dailyBudgetUsd), bar('Questo mese', u.monthUsd, u.monthlyBudgetUsd),
      u.byModel.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'lb usage' },
        h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Modello'), h('th', { scope: 'col', class: 'c-bal' }, 'Chiamate'), h('th', { scope: 'col', class: 'c-bal' }, 'Costo'))),
        h('tbody', null, u.byModel.map((m) => h('tr', null, h('td', { class: 'mono' }, m.model), h('td', { class: 'c-bal' }, fmt(m.calls)), h('td', { class: 'c-bal' }, usd.format(m.costUsd))))))) : h('p', { class: 'muted empty' }, 'Nessuna chiamata registrata.'));
  }
  load();

  function update() {
    const s = store.state;
    if (!s) return;
    region(mods, JSON.stringify(s.modules), () => modsCard(s.modules));
    const all = [{ id: store.me.id, name: store.me.name + ' (tu)' }, ...s.members];
    fillSelect(sel, all, 'Scegli un membro…');
  }
  return { update };
}
