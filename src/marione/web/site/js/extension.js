// The "browser extension" dialog on the soundboard page: download, connect (one click), disconnect.
// The extension's content script (extension/pair.js) answers the messages posted here.
import { fill, h } from './util.js';
import { post } from './api.js';
import { handleError } from './data.js';
import { toast } from './toast.js';
import { t } from './i18n.js';
import { btn, modal } from './ui.js';

const installed = () => document.documentElement.dataset.marioneExt === '1';

export function openExtension() {
  const status = h('p', { class: 'ext-status', role: 'status' });
  const actions = h('div', { class: 'ext-actions' });
  let paired = false, name = null;

  const draw = () => {
    status.className = 'ext-status ' + (paired ? 'ok' : '');
    status.textContent = !installed() ? '⚠️ ' + t('ext.notFound')
      : paired ? '✅ ' + t('ext.connected', { name: name || '' }) : '🔌 ' + t('ext.notConnected');
    fill(actions,
      installed() && !paired ? btn(t('ext.connect'), 'primary', { onclick: connect }) : null,
      installed() && paired ? btn(t('ext.disconnect'), 'ghost', { onclick: disconnect }) : null);
  };
  const ask = () => window.postMessage({ type: 'marione-ext-ping' }, location.origin);
  const onMessage = (e) => {
    if (e.source !== window || e.origin !== location.origin || !e.data) return;
    if (e.data.type === 'marione-ext-pong') { paired = !!e.data.paired; name = e.data.name; draw(); }
    if (e.data.type === 'marione-ext-paired') {
      if (e.data.ok) { paired = true; name = e.data.name; toast(t('ext.paired')); } else toast(e.data.message || t('common.unexpected'), 'err');
      draw();
    }
  };
  async function connect(e) {
    e.currentTarget.disabled = true;
    try {
      const r = await post('/api/ext/token');
      window.postMessage({ type: 'marione-pair', token: r.token }, location.origin);
    } catch (err) { handleError(err); draw(); }
  }
  async function disconnect() {
    try {
      await post('/api/ext/revoke'); // every browser loses access
      window.postMessage({ type: 'marione-unpair' }, location.origin);
      toast(t('ext.disconnected'));
    } catch (err) { handleError(err); }
  }

  const body = h('div', { class: 'stack' },
    h('p', null, t('ext.intro')),
    status, actions,
    h('ol', { class: 'ext-steps' },
      h('li', null, h('a', { class: 'btn ghost sm', href: '/marione-extension.zip', download: '' }, '⬇️ ' + t('ext.download')), ' ', t('ext.step1')),
      h('li', null, t('ext.step2')),
      h('li', null, t('ext.step3')),
      h('li', null, t('ext.step4'))),
    h('p', { class: 'muted small' }, t('ext.limits')));
  const { dlg } = modal(t('ext.title'), body, (close) => [btn(t('common.close'), 'primary', { onclick: close })]);
  window.addEventListener('message', onMessage);
  dlg.addEventListener('close', () => window.removeEventListener('message', onMessage));
  draw();
  if (installed()) ask();
}
