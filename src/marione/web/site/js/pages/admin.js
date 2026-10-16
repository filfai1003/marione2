// Admin hub: on phones the "Admin" tab opens this page, which leads to each admin tool.
import { h } from '../util.js';
import { t } from '../i18n.js';
import { pageHead } from '../ui.js';

const TOOLS = [
  ['entrances', '🎺', 'admin.entrancesSub'],
  ['brain', '🧠', 'admin.brainSub'],
  ['settings', '⚙️', 'admin.settingsSub'],
];

export function mount(root) {
  root.append(pageHead(t('nav.admin'), t('admin.sub')),
    h('div', { class: 'hub' }, TOOLS.map(([k, emoji, sub]) => h('a', { class: 'quick', href: '#/' + k },
      h('span', { class: 'q-emoji', 'aria-hidden': 'true' }, emoji),
      h('span', null, h('strong', null, t('nav.' + k)), h('small', null, t(sub)))))));
  return { update() {} };
}
