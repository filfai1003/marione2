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
  const sounds = ((config && config.sounds) || []).filter((x) => x.shortcut);
  box.append(el('p', {}, 'Connected as ', el('b', {}, config ? config.me.name : '…')),
    el('p', { className: 'muted' }, 'These keys work on every tab (reload tabs opened before installing):'));
  const list = el('ol');
  for (const s of sounds) list.append(el('li', {}, el('b', {}, s.shortcut.replace('Ctrl+', '')), el('span', {}, (s.emoji || '🔊') + ' ' + s.name)));
  if (!sounds.length) list.append(el('li', { className: 'empty' }, el('span', {}, 'No sounds yet: add some on the Soundboard page.')));
  box.append(list,
    el('button', { onclick: async () => { await ext.runtime.sendMessage({ type: 'refresh' }); draw(); } }, 'Refresh'),
    el('button', { onclick: () => ext.tabs.create({ url: 'chrome://extensions/shortcuts' }) }, 'Global keys'),
    el('p', { className: 'muted' }, 'To play with the browser in the background (games), set the scope of “Ctrl+Shift+1…4” to Global there: they play your first four sounds. Star a sound to move it up the list.'));
}

draw();
