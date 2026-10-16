import { h, fmt, abbrev, region, avatar, debounce, mmss, ago } from '../util.js';
import { store, subscribe, robRemaining, setRobCooldown } from '../store.js';
import { api, post } from '../api.js';
import { run, refreshState, setBalance, handleError } from '../data.js';
import { toast } from '../toast.js';
import { card, cardTitle, pageHead, notice, tierBadge, field, btn, fillSelect, historyList } from '../ui.js';
import { safeColor } from '../util.js';

const num = (el) => { const v = Math.floor(Number(el.value)); return Number.isFinite(v) && v > 0 ? v : 0; };

export function mount(root) {
  const head = pageHead('Economia', 'Marioncelli, furti e classifica della tavolata.');
  const body = h('div', { class: 'stack-lg' });
  root.append(head, body);
  const slots = { off: h('div'), forms: h('div', { class: 'grid g-2' }), board: h('div'), lower: h('div', { class: 'grid g-2' }) };
  body.append(...Object.values(slots));
  const roles = h('div'), hist = h('div');
  slots.lower.append(roles, hist);

  // ---------- Manda Marioncelli ----------
  const paySel = h('select', { required: true });
  const payAmt = h('input', { type: 'number', min: '1', step: '1', inputmode: 'numeric', placeholder: 'Quanti?' });
  const payBtn = btn('Manda 💸', 'primary block', { type: 'submit' });
  const chips = [10, 50, 100, 500].map((n) => h('button', { type: 'button', class: 'chip-btn', onclick: () => { payAmt.value = n; payAmt.focus(); } }, '+' + n));
  const payForm = h('form', { class: 'stack', onsubmit: (e) => {
    e.preventDefault();
    const amount = num(payAmt);
    if (!paySel.value) { toast('Scegli a chi mandare i Marioncelli.', 'err'); paySel.focus(); return; }
    if (!amount) { toast('Inserisci un importo valido.', 'err'); payAmt.focus(); return; }
    if (amount > store.balance) { toast('Non hai abbastanza Marioncelli 🪙', 'err'); return; }
    run(payBtn, async () => {
      const r = await post('/api/economy/pay', { memberId: paySel.value, amount });
      setBalance(r.balance);
      toast(r.message || 'Fatto!');
      payAmt.value = '';
      await refreshState();
    });
  } }, field('A chi?', paySel), field('Quanto?', payAmt), h('div', { class: 'chips' }, chips), payBtn);
  const payCard = card('', cardTitle('💸', 'Manda Marioncelli'), payForm);

  // ---------- Furto ----------
  const robSel = h('select', { required: true });
  const robAmt = h('input', { type: 'number', min: '1', step: '1', inputmode: 'numeric', placeholder: 'Quanto vuoi rubare?' });
  const meter = h('div', { class: 'meter idle' });
  const cdEl = h('p', { class: 'cooldown', 'aria-live': 'off' });
  const robBtn = btn('Tenta il furto 🦹', 'danger block', { type: 'submit' });
  const banner = h('div');
  let armed = false, armTimer, seq = 0, previewOk = false;

  const setMeter = (kind, r, msg) => {
    meter.className = 'meter ' + kind;
    if (kind === 'ok') {
      const pct = Math.round(r.prob * 100);
      const lvl = pct < 25 ? 'low' : pct < 50 ? 'mid' : 'high';
      meter.classList.add(lvl);
      meter.replaceChildren(
        h('div', { class: 'meter-top' }, h('span', { class: 'meter-pct' }, pct + '%'), h('span', null, 'di riuscita')),
        h('div', { class: 'meter-track', role: 'meter', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(pct), 'aria-label': 'Probabilità di successo' },
          h('div', { class: 'meter-fill', style: { width: Math.max(2, pct) + '%' } })),
        h('p', null, 'Se ti beccano paghi ~', h('strong', null, fmt(r.fine) + ' 🪙')));
    } else meter.replaceChildren(h('p', { class: 'muted' }, msg));
  };
  setMeter('idle', null, 'Scegli vittima e importo per vedere le probabilità.');

  const syncRob = () => {
    const cd = robRemaining();
    cdEl.textContent = cd > 0 ? `⏳ Prossimo furto tra ${mmss(cd)}` : '';
    cdEl.hidden = cd <= 0;
    if (!robBtn.dataset.busy) robBtn.disabled = cd > 0;
    robBtn.textContent = armed ? 'Sicuro? Clicca di nuovo!' : 'Tenta il furto 🦹';
  };
  const disarm = () => { armed = false; clearTimeout(armTimer); syncRob(); };

  const preview = debounce(async () => {
    const id = ++seq, amount = num(robAmt);
    try {
      const r = await api(`/api/economy/rob-preview?victimId=${encodeURIComponent(robSel.value)}&amount=${amount}`);
      if (id !== seq) return;
      previewOk = true;
      if (r.cooldownSeconds != null) setRobCooldown(r.cooldownSeconds);
      setMeter('ok', r);
    } catch (e) {
      if (id !== seq) return;
      previewOk = false;
      setMeter('idle', null, e.message);
    }
  }, 300);
  const onRobInput = () => {
    disarm();
    seq++;
    if (!robSel.value || !num(robAmt)) { preview.cancel(); previewOk = false; setMeter('idle', null, 'Scegli vittima e importo per vedere le probabilità.'); return; }
    meter.classList.add('loading');
    preview();
  };
  robSel.addEventListener('change', onRobInput);
  robAmt.addEventListener('input', onRobInput);

  const showResult = (r) => {
    const ok = r.success;
    banner.replaceChildren(h('div', { class: 'result ' + (ok ? 'win' : 'lose'), role: 'status' },
      h('span', { class: 'result-emoji', 'aria-hidden': 'true' }, ok ? '💰' : '🚓'),
      h('div', null, h('strong', null, ok ? 'Colpo riuscito!' : 'Ti hanno beccato!'), h('p', null, r.message),
        h('p', { class: 'result-amt' }, ok ? '+' + fmt(r.amount) + ' 🪙' : '−' + fmt(r.fine) + ' 🪙 di multa')),
      h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Chiudi', onclick: () => banner.replaceChildren() }, '✕')));
  };

  const robForm = h('form', { class: 'stack', onsubmit: (e) => {
    e.preventDefault();
    if (robRemaining() > 0) return;
    if (!robSel.value || !num(robAmt)) { toast('Scegli una vittima e un importo.', 'err'); return; }
    if (!armed) { armed = true; syncRob(); armTimer = setTimeout(disarm, 4000); return; }
    disarm();
    run(robBtn, async () => {
      const r = await post('/api/economy/rob', { victimId: robSel.value, amount: num(robAmt) });
      setBalance(r.balance);
      setRobCooldown(r.cooldownSeconds);
      showResult(r);
      await refreshState();
    }).then(syncRob);
  } }, banner, field('Vittima', robSel), field('Importo', robAmt), meter, cdEl, robBtn);
  const robCard = card('rob-card', cardTitle('🦹', 'Furto', h('span', { class: 'tag danger' }, 'rischioso')), robForm);

  // ---------- Classifica ----------
  const medal = (i) => ['🥇', '🥈', '🥉'][i] || '#' + (i + 1);
  const board = (lb) => card('', cardTitle('🏆', 'Classifica'),
    h('div', { class: 'table-wrap' }, h('table', { class: 'lb' },
      h('thead', null, h('tr', null, h('th', { scope: 'col', class: 'c-rank' }, '#'), h('th', { scope: 'col' }, 'Commensale'),
        h('th', { scope: 'col', class: 'c-tier' }, 'Ruolo'), h('th', { scope: 'col', class: 'c-bal' }, 'Saldo'))),
      h('tbody', null, lb.map((r, i) => h('tr', { class: r.isMe ? 'is-me' : '' },
        h('td', { class: 'c-rank' }, medal(i)),
        h('td', { class: 'c-name' }, h('span', { class: 'who' }, avatar(r, 32), h('span', { class: 'who-name' }, r.name), r.isMe ? h('span', { class: 'tag' }, 'tu') : null,
          h('span', { class: 'tier-mini', title: r.tier.name }, r.tier.emoji))),
        h('td', { class: 'c-tier' }, tierBadge(r.tier)),
        h('td', { class: 'c-bal' }, h('span', { title: fmt(r.bal) }, abbrev(r.bal)), ' 🪙')))))));

  const rolesCard = (list, cur) => card('', cardTitle('🎖️', 'Ruoli'),
    h('p', { class: 'muted small' }, 'Più Marioncelli hai, più sali. Il ruolo si assegna da solo sul server.'),
    h('ul', { class: 'roles' }, list.map((r) => h('li', { class: 'role' + (r.min === cur.min ? ' now' : ''), style: { '--c': safeColor(r.color) } },
      h('span', { class: 'role-emoji' }, r.emoji), h('span', { class: 'role-name' }, r.name),
      h('span', { class: 'role-min' }, r.min ? 'da ' + fmt(r.min) + ' 🪙' : 'per tutti'),
      r.min === cur.min ? h('span', { class: 'tag' }, 'tu sei qui') : null))));

  function update() {
    const s = store.state;
    if (!s) return;
    const m = s.modules;
    region(slots.off, m.economy ? 'on' : 'off', () => m.economy ? null
      : notice('🍝', 'Economia in pausa', 'I Marioncelli sono in pausa: niente pagamenti, furti o classifica per ora.'));
    slots.forms.hidden = slots.board.hidden = slots.lower.hidden = !m.economy;
    if (!m.economy) return;
    fillSelect(paySel, s.members, 'Scegli un commensale…');
    fillSelect(robSel, s.members, 'Scegli la vittima…');
    region(slots.forms, m.rob ? 'rob' : 'norob', () => { slots.forms.classList.toggle('one', !m.rob); return [payCard, m.rob ? robCard : null]; });
    region(slots.board, JSON.stringify(s.leaderboard), () => board(s.leaderboard));
    region(roles, m.roles ? JSON.stringify([s.roles, s.tier.min]) : 'off', () => m.roles ? rolesCard(s.roles, s.tier) : null);
    region(hist, JSON.stringify(s.history), () => card('', cardTitle('📒', 'Movimenti'), historyList(s.history)));
    slots.lower.classList.toggle('one', !m.roles);
    syncRob();
  }
  return { update, tick: syncRob, destroy() { preview.cancel(); clearTimeout(armTimer); } };
}
