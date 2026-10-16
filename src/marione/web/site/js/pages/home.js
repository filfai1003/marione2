import { h, fmt, region } from '../util.js';
import { store } from '../store.js';
import { t } from '../i18n.js';
import { card, cardTitle, pageHead, tierBadge, progress, historyList, notice } from '../ui.js';

export function mount(root) {
  const R = { greet: h('div'), main: h('div', { class: 'grid g-main' }), quick: h('div'), hist: h('div') };
  root.append(R.greet, R.main, R.quick, R.hist);

  function balanceCard(s) {
    const tier = s.tier, bal = store.balance;
    let prog = null;
    if (tier.next) {
      const span = Math.max(1, tier.next.min - tier.min);
      const missing = Math.max(0, tier.next.min - bal);
      prog = h('div', { class: 'tier-prog' },
        progress(((bal - tier.min) / span) * 100, t('home.progressAria')),
        h('p', null, t('home.missing', { amount: fmt(missing) }), ' ', h('span', { class: 'muted' }, '(' + tier.next.name + ')')));
    }
    return card('balance-card',
      h('span', { class: 'eyebrow' }, t('home.wallet')),
      h('div', { class: 'bignum' }, h('span', { class: 'coin-big', 'aria-hidden': 'true' }, '🪙'), fmt(bal)),
      h('div', { class: 'tier-row' }, tierBadge(tier)), prog);
  }

  function rankCard(s) {
    return card('rank-card',
      h('span', { class: 'eyebrow' }, t('home.position')),
      h('div', { class: 'bignum rank' }, s.rank ? '#' + s.rank : '—'),
      h('p', null, t('home.ofTable', { count: fmt(s.memberCount) })),
      h('a', { class: 'link', href: '#/economy/leaderboard' }, t('home.seeLeaderboard') + ' →'),
      h('div', { class: 'rank-emoji mar-anim-bob', 'aria-hidden': 'true' }, '🍽️'));
  }

  function quick(s) {
    const m = s.modules;
    const q = (href, emoji, title, sub, cls = '') => h('a', { class: 'quick ' + cls, href },
      h('span', { class: 'q-emoji', 'aria-hidden': 'true' }, emoji), h('span', null, h('strong', null, title), h('small', null, sub)));
    return h('div', { class: 'grid g-quick' },
      m.economy ? q('#/economy/send', '💸', t('home.qSend'), t('home.qSendSub')) : null,
      m.economy && m.rob ? q('#/economy/heist', '🦹', t('home.qRob'), t('home.qRobSub'), 'danger') : null,
      m.soundboard ? q('#/soundboard', '🔊', t('home.qBoard'), t('home.qBoardSub'), 'green') : null);
  }

  function update() {
    const s = store.state;
    if (!s) return;
    const eco = s.modules.economy;
    region(R.greet, s.me.name + t('home.hello'), () => pageHead(t('home.hello', { name: s.me.name }), t('home.sub')));
    region(R.main, eco ? JSON.stringify([store.balance, s.tier, s.rank, s.memberCount, t('home.wallet')]) : 'off', () => eco
      ? [balanceCard(s), rankCard(s)]
      : notice('🍝', t('eco.pausedTitle'), t('eco.pausedText')));
    region(R.quick, JSON.stringify([s.modules, t('home.qSend')]), () => quick(s));
    const recent = s.history.slice(0, 5);
    region(R.hist, eco ? JSON.stringify([recent, t('home.recent')]) : 'off', () => eco
      ? card('', cardTitle('📒', t('home.recent'), h('a', { class: 'link', href: '#/economy/history' }, t('common.seeAll') + ' →')), historyList(recent))
      : null);
  }
  return { update };
}
