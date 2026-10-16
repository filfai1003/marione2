import { h, fmt, region } from '../util.js';
import { store } from '../store.js';
import { card, cardTitle, pageHead, tierBadge, progress, historyList, notice } from '../ui.js';

export function mount(root) {
  const R = { greet: h('div'), main: h('div', { class: 'grid g-main' }), quick: h('div'), hist: h('div') };
  root.append(R.greet, R.main, R.quick, R.hist);

  function balanceCard(s) {
    const t = s.tier, bal = store.balance;
    let prog = null;
    if (t.next) {
      const span = Math.max(1, t.next.min - t.min);
      const missing = Math.max(0, t.next.min - bal);
      prog = h('div', { class: 'tier-prog' },
        progress(((bal - t.min) / span) * 100, 'Avanzamento verso il prossimo ruolo'),
        h('p', null, 'Ti mancano ', h('strong', null, fmt(missing) + ' 🪙'), ' per salire di ruolo ',
          h('span', { class: 'muted' }, '(' + t.next.name + ')')));
    }
    return card('balance-card',
      h('span', { class: 'eyebrow' }, 'Il tuo portafoglio'),
      h('div', { class: 'bignum' }, h('span', { class: 'coin-big', 'aria-hidden': 'true' }, '🪙'), fmt(bal)),
      h('div', { class: 'tier-row' }, tierBadge(t)), prog);
  }

  function rankCard(s) {
    return card('rank-card',
      h('span', { class: 'eyebrow' }, 'La tua posizione'),
      h('div', { class: 'bignum rank' }, '#' + s.rank),
      h('p', null, 'su ' + fmt(s.memberCount) + ' a tavola'),
      h('div', { class: 'rank-emoji mar-anim-bob', 'aria-hidden': 'true' }, '🍽️'));
  }

  function quick(s) {
    const m = s.modules;
    const q = (href, emoji, title, sub, cls = '') => h('a', { class: 'quick ' + cls, href }, h('span', { class: 'q-emoji' }, emoji), h('span', null, h('strong', null, title), h('small', null, sub)));
    return h('div', { class: 'grid g-quick' },
      m.economy ? q('#/economia', '💸', 'Manda Marioncelli', 'Offri un caffè a qualcuno') : null,
      m.economy && m.rob ? q('#/economia', '🦹', 'Furto', 'Tenta il colpo grosso', 'danger') : null,
      m.soundboard ? q('#/soundboard', '🔊', 'Soundboard', 'Fai casino in vocale') : null);
  }

  function update() {
    const s = store.state;
    if (!s) return;
    const eco = s.modules.economy;
    region(R.greet, s.me.name, () => pageHead(`Ciao, ${s.me.name} 👋`, 'Si mangia? Ecco come va il tuo conto.'));
    region(R.main, eco ? JSON.stringify([store.balance, s.tier, s.rank, s.memberCount]) : 'off', () => eco
      ? [balanceCard(s), rankCard(s)]
      : notice('🍝', 'Economia in pausa', 'Gli amministratori hanno messo in pausa i Marioncelli. Torna a trovarci presto: intanto puoi usare il resto del locale.'));
    region(R.quick, JSON.stringify(s.modules), () => quick(s));
    region(R.hist, eco ? JSON.stringify(s.history.slice(0, 5)) : 'off', () => eco
      ? card('', cardTitle('📒', 'Ultimi movimenti', h('a', { class: 'link', href: '#/economia' }, 'Vedi tutto')), historyList(s.history.slice(0, 5)))
      : null);
  }
  return { update };
}
