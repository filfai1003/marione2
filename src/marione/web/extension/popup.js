const ext = globalThis.browser ?? globalThis.chrome;
const ORIGIN = '__ORIGIN__';
const box = document.getElementById('state');

const el = (tag, props, ...kids) => {
  const node = Object.assign(document.createElement(tag), props || {});
  node.append(...kids.filter((k) => k != null));
  return node;
};

async function draw() {
  const { token, config } = await ext.storage.local.get(['token', 'config']);
  box.replaceChildren();
  if (!token) {
    box.append(
      el('p', {}, 'Not connected yet.'),
      el('p', { className: 'muted' }, 'Open Marione, go to the Soundboard page and press “Connect the browser extension”.'),
      el('a', { className: 'btn', href: ORIGIN + '/#/soundboard', target: '_blank' }, 'Open Marione'));
    return;
  }
  const sounds = (config && config.sounds) || [];
  box.append(el('p', {}, 'Connected as ', el('b', {}, config ? config.me.name : '…')));
  const list = el('ol');
  for (let slot = 1; slot <= 4; slot++) {
    const s = sounds.find((x) => x.slot === slot);
    list.append(el('li', { className: s ? '' : 'empty' }, el('b', {}, String(slot)),
      el('span', {}, s ? (s.emoji || '🔊') + ' ' + s.name : 'No sound: choose one on the Soundboard page')));
  }
  box.append(el('p', { className: 'muted' }, 'Global slots (work with the browser in the background):'), list,
    el('button', { onclick: () => ext.tabs.create({ url: 'chrome://extensions/shortcuts' }) }, 'Set the keys'),
    el('button', { onclick: async () => { await ext.runtime.sendMessage({ type: 'refresh' }); draw(); } }, 'Refresh'),
    el('p', { className: 'muted' }, 'In the keys page, set each “Global slot” key to scope “Global”. Your other shortcuts work on every tab while the browser is in front.'));
}

draw();
