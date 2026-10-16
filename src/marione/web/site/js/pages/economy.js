// Economy: one task per tab (send · heist · leaderboard · history) instead of one long page.
import { fill, h, fmt, abbrev, region, avatar, debounce, mmss, safeColor } from '../util.js';
import { store, robRemaining, setRobCooldown } from '../store.js';
import { api, post } from '../api.js';
import { run, refreshState, setBalance, handleError } from '../data.js';
import { toast } from '../toast.js';
import { t } from '../i18n.js';
import { card, cardTitle, pageHead, notice, tierBadge, field, btn, fillSelect, historyList,
  tabs, pager, searchBox, fieldError, empty, modal } from '../ui.js';

const PAGE = 10;
const num = (el) => { const v = Math.floor(Number(el.value)); return Number.isFinite(v) && v > 0 ? v : 0; };

export function mount(root, sub) {
  let tab = sub || 'send';
  const head = pageHead(t('eco.title'), t('eco.sub'));
  const off = h('div');
  const tabBox = h('div');
  const panel = h('div', { class: 'tab-panel', role: 'tabpanel', tabindex: '-1' });
  root.append(head, off, tabBox, panel);
  let tabbar = null, tabKey = '';

  // ---------- send ----------
  const paySel = h('select', { required: true, 'aria-label': t('eco.to') });
  const payAmt = h('input', { type: 'number', min: '1', step: '1', inputmode: 'numeric', placeholder: t('eco.amountPh') });
  const payErr = fieldError();
  const payBtn = btn(t('eco.sendBtn') + ' 💸', 'primary block', { type: 'submit' });
  const chips = [10, 50, 100, 500].map((n) => h('button', { type: 'button', class: 'chip-btn', onclick: () => { payAmt.value = n; payErr.show(''); payAmt.focus(); } }, '+' + n));
  const payForm = h('form', { class: 'stack', novalidate: true, onsubmit: (e) => {
    e.preventDefault();
    const amount = num(payAmt);
    if (!paySel.value) { payErr.show(t('eco.errPickMember')); paySel.focus(); return; }
    if (!amount) { payErr.show(t('eco.errAmount')); payAmt.focus(); return; }
    if (amount > store.balance) { payErr.show(t('eco.errNotEnough')); payAmt.focus(); return; }
    payErr.show('');
    run(payBtn, async () => {
      const r = await post('/api/economy/pay', { memberId: paySel.value, amount });
      setBalance(r.balance);
      toast(r.message);
      payAmt.value = '';
      await refreshState();
    });
  } }, field(t('eco.to'), paySel), field(t('eco.amount'), payAmt, t('eco.available', { amount: '' }), payErr.el),
  h('div', { class: 'chips' }, chips), payBtn);
  const availHint = payForm.querySelector('.hint');
  const sendPanel = card('narrow', cardTitle('💸', t('eco.sendTitle')), payForm);

  // ---------- heist ----------
  const robSel = h('select', { required: true, 'aria-label': t('eco.victim') });
  const robAmt = h('input', { type: 'number', min: '1', step: '1', inputmode: 'numeric', placeholder: t('eco.robPh') });
  const meter = h('div', { class: 'meter idle', 'aria-live': 'polite' });
  const cdEl = h('p', { class: 'cooldown' });
  const robBtn = btn(t('eco.robBtn') + ' 🦹', 'danger block', { type: 'submit' });
  const banner = h('div');
  let seq = 0;

  const setMeter = (kind, r, msg) => {
    meter.className = 'meter ' + kind;
    if (kind === 'ok') {
      const pct = Math.round(r.prob * 100);
      meter.classList.add(pct < 25 ? 'low' : pct < 50 ? 'mid' : 'high');
      fill(meter, 
        h('div', { class: 'meter-top' }, h('span', { class: 'meter-pct' }, pct + '%'), h('span', null, t('eco.chance'))),
        h('div', { class: 'meter-track', role: 'meter', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(pct), 'aria-label': t('eco.chance') },
          h('div', { class: 'meter-fill', style: { width: Math.max(2, pct) + '%' } })),
        h('p', null, t('eco.fineIf', { amount: fmt(r.fine) })));
    } else fill(meter, h('p', { class: 'muted' }, msg));
  };
  setMeter('idle', null, t('eco.pickToSee'));

  const syncRob = () => {
    const cd = robRemaining();
    cdEl.textContent = cd > 0 ? '⏳ ' + t('eco.nextIn', { time: mmss(cd) }) : '';
    cdEl.hidden = cd <= 0;
    if (!robBtn.dataset.busy) robBtn.disabled = cd > 0;
  };

  const previewOdds = debounce(async () => {
    const id = ++seq, amount = num(robAmt);
    try {
      const r = await api(`/api/economy/rob-preview?victimId=${encodeURIComponent(robSel.value)}&amount=${amount}`);
      if (id !== seq) return;
      if (r.cooldownSeconds != null) setRobCooldown(r.cooldownSeconds);
      setMeter('ok', r);
    } catch (e) {
      if (id === seq) setMeter('idle', null, e.message);
    }
  }, 300);
  const onRobInput = () => {
    seq++;
    if (!robSel.value || !num(robAmt)) { previewOdds.cancel(); setMeter('idle', null, t('eco.pickToSee')); return; }
    meter.classList.add('loading');
    previewOdds();
  };
  robSel.addEventListener('change', onRobInput);
  robAmt.addEventListener('input', onRobInput);

  const showResult = (r) => {
    const ok = r.success;
    fill(banner, h('div', { class: 'result ' + (ok ? 'win' : 'lose'), role: 'status' },
      h('span', { class: 'result-emoji', 'aria-hidden': 'true' }, ok ? '💰' : '🚓'),
      h('div', null, h('strong', null, ok ? t('eco.won') : t('eco.caught')), h('p', null, r.message),
        h('p', { class: 'result-amt' }, ok ? '+' + fmt(r.amount) + ' 🪙' : t('eco.fineAmt', { amount: fmt(r.fine) }))),
      h('button', { type: 'button', class: 'icon-btn', 'aria-label': t('common.close'), onclick: () => banner.replaceChildren() }, '✕')));
  };

  // Destructive and irreversible: always confirm, with the real numbers.
  const confirmRob = (victimName, amount) => new Promise((resolve) => {
    const { dlg } = modal(t('eco.confirmTitle'), h('p', null, t('eco.confirmText', { name: victimName, amount: fmt(amount) })), (close) => [
      btn(t('common.cancel'), 'ghost', { onclick: () => { resolve(false); close(); } }),
      btn(t('eco.robBtn') + ' 🦹', 'danger', { onclick: () => { resolve(true); close(); } }),
    ]);
    dlg.addEventListener('close', () => resolve(false));
  });

  const robForm = h('form', { class: 'stack', novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (robRemaining() > 0) return;
    if (!robSel.value || !num(robAmt)) { toast(t('eco.errPickVictim'), 'err'); return; }
    const name = robSel.options[robSel.selectedIndex].textContent;
    if (!(await confirmRob(name, num(robAmt)))) return;
    run(robBtn, async () => {
      const r = await post('/api/economy/rob', { victimId: robSel.value, amount: num(robAmt) });
      setBalance(r.balance);
      setRobCooldown(r.cooldownSeconds);
      showResult(r);
      await refreshState();
    }).then(syncRob);
  } }, banner, field(t('eco.victim'), robSel), field(t('eco.amount'), robAmt), meter, cdEl, robBtn,
  h('p', { class: 'hint center' }, t('eco.robHint')));
  const robPanel = card('narrow rob-card', cardTitle('🦹', t('eco.robTitle'), h('span', { class: 'tag danger' }, t('eco.risky'))), robForm);

  // ---------- leaderboard (paginated, searchable) ----------
  const lb = { q: '', offset: 0, total: 0, items: null, seq: 0 };
  const lbBody = h('div', { class: 'stack' });
  const lbSearch = searchBox(t('eco.searchMember'), (q) => { lb.q = q; loadBoard(0); });
  const meBtn = btn('📍 ' + t('eco.jumpMe'), 'ghost sm', { onclick: () => {
    lb.q = ''; lbSearch.input.value = '';
    const s = store.state;
    loadBoard(s && s.rank ? Math.floor((s.rank - 1) / PAGE) * PAGE : 0, true);
  } });
  const medal = (rank) => ['🥇', '🥈', '🥉'][rank - 1] || '#' + rank;
  const boardTable = (items) => h('div', { class: 'table-wrap' }, h('table', { class: 'lb' },
    h('caption', { class: 'sr-only' }, t('eco.board')),
    h('thead', null, h('tr', null, h('th', { scope: 'col', class: 'c-rank' }, '#'), h('th', { scope: 'col' }, t('eco.colMember')),
      h('th', { scope: 'col', class: 'c-tier' }, t('eco.colRole')), h('th', { scope: 'col', class: 'c-bal' }, t('eco.colBalance')))),
    h('tbody', null, items.map((r) => h('tr', { class: r.isMe ? 'is-me' : '' },
      h('td', { class: 'c-rank' }, medal(r.rank)),
      h('td', { class: 'c-name' }, h('span', { class: 'who' }, avatar(r, 32), h('span', { class: 'who-name' }, r.name), r.isMe ? h('span', { class: 'tag' }, t('common.you')) : null,
        h('span', { class: 'tier-mini', title: r.tier.name }, r.tier.emoji))),
      h('td', { class: 'c-tier' }, tierBadge(r.tier)),
      h('td', { class: 'c-bal' }, h('span', { title: fmt(r.bal) }, abbrev(r.bal)), ' 🪙'))))));
  function drawBoard(flash) {
    fill(lbBody, 
      lb.items === null ? h('p', { class: 'muted center' }, t('common.loading'))
        : lb.items.length ? boardTable(lb.items) : empty('🔎', lb.q ? t('eco.noMatch', { q: lb.q }) : t('eco.nobodyRich')),
      pager(lb.total, lb.offset, PAGE, (o) => loadBoard(o)));
    if (flash) { const row = lbBody.querySelector('tr.is-me'); if (row) row.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
  }
  async function loadBoard(offset, flash = false) {
    const id = ++lb.seq;
    try {
      const r = await api(`/api/economy/leaderboard?offset=${offset}&limit=${PAGE}&q=${encodeURIComponent(lb.q)}`);
      if (id !== lb.seq) return;
      Object.assign(lb, { offset, total: r.total, items: r.items });
      drawBoard(flash);
    } catch (e) { handleError(e); }
  }
  const rolesBox = h('div');
  const rolesCard = (list, cur) => h('details', { class: 'card fold' },
    h('summary', null, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, '🎖️'),
      h('span', { class: 'fold-title' }, h('h2', null, t('eco.rolesTitle')), h('small', null, t('eco.rolesSub'))), h('span', { class: 'fold-chev', 'aria-hidden': 'true' }, '▾')),
    h('div', { class: 'fold-body' }, h('ul', { class: 'roles' }, list.map((r) => h('li', { class: 'role' + (r.min === cur.min ? ' now' : ''), style: { '--c': safeColor(r.color) } },
      h('span', { class: 'role-emoji' }, r.emoji), h('span', { class: 'role-name' }, r.name),
      h('span', { class: 'role-min' }, r.min ? t('eco.from', { amount: fmt(r.min) }) : t('eco.forAll')),
      r.min === cur.min ? h('span', { class: 'tag' }, t('eco.youAreHere')) : null)))));
  const boardPanel = h('div', { class: 'stack-lg' },
    card('', cardTitle('🏆', t('eco.board'), meBtn), h('div', { class: 'toolbar' }, lbSearch.el), lbBody), rolesBox);

  // ---------- history (paginated) ----------
  const hs = { offset: 0, total: 0, items: null, seq: 0 };
  const histBody = h('div', { class: 'stack' });
  async function loadHistory(offset) {
    const id = ++hs.seq;
    try {
      const r = await api(`/api/economy/history?offset=${offset}&limit=${PAGE}`);
      if (id !== hs.seq) return;
      Object.assign(hs, { offset, total: r.total, items: r.items });
      fill(histBody, historyList(hs.items), pager(hs.total, hs.offset, PAGE, loadHistory));
    } catch (e) { handleError(e); }
  }
  const histPanel = card('', cardTitle('📒', t('eco.historyTitle')), histBody);

  // ---------- tabs ----------
  function tabItems(m) {
    return [['send', '💸', t('eco.tabSend')], m.rob ? ['heist', '🦹', t('eco.tabRob')] : null,
      ['leaderboard', '🏆', t('eco.tabBoard')], ['history', '📒', t('eco.tabHistory')]].filter(Boolean);
  }
  function show(key, fromUser) {
    const s = store.state;
    const items = tabItems(s.modules).map((x) => x[0]);
    if (!items.includes(key)) key = 'send';
    tab = key;
    if (tabbar) tabbar.select(key);
    panel.setAttribute('aria-labelledby', 'tab-' + key);
    const view = { send: sendPanel, heist: robPanel, leaderboard: boardPanel, history: histPanel }[key];
    fill(panel, view);
    if (key === 'leaderboard') { if (lb.items === null) { lb.items = s.leaderboard; lb.total = s.leaderboardTotal; } drawBoard(); loadBoard(lb.offset); }
    if (key === 'history') loadHistory(0);
    if (fromUser && location.hash !== '#/economy/' + key) history.replaceState(null, '', '#/economy/' + key);
  }

  function update() {
    const s = store.state;
    if (!s) return;
    const m = s.modules;
    region(off, m.economy ? 'on' : 'off', () => m.economy ? null : notice('🍝', t('eco.pausedTitle'), t('eco.pausedText')));
    tabBox.hidden = panel.hidden = !m.economy;
    if (!m.economy) return;
    const key = JSON.stringify(tabItems(m));
    if (key !== tabKey) {
      tabKey = key;
      tabbar = tabs(tabItems(m), tab, (k) => show(k, true));
      fill(tabBox, tabbar.el);
      show(tab);
    }
    fillSelect(paySel, s.members, t('eco.pickMember'));
    fillSelect(robSel, s.members, t('eco.pickVictim'));
    availHint.textContent = t('eco.available', { amount: fmt(store.balance) });
    region(rolesBox, m.roles ? JSON.stringify([s.roles, s.tier.min]) : 'off', () => m.roles ? rolesCard(s.roles, s.tier) : null);
    syncRob();
  }
  return {
    update, tick: syncRob,
    route(next) { show(next || 'send'); },
    destroy() { previewOdds.cancel(); lbSearch.cancel(); },
  };
}
