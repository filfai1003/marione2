import { h } from './util.js';

let box;
export function toast(msg, type = 'ok', ms = 4200) {
  if (!box) {
    box = h('div', { class: 'toasts', role: 'status', 'aria-live': 'polite' });
    document.body.append(box);
  }
  const t = h('button', { class: 'toast ' + type, type: 'button' },
    h('span', { class: 'toast-ico', 'aria-hidden': 'true' }, type === 'err' ? '⚠️' : type === 'info' ? '💡' : '✅'),
    h('span', null, msg));
  const kill = () => { t.classList.add('out'); setTimeout(() => t.remove(), 200); };
  t.addEventListener('click', kill);
  box.append(t);
  while (box.children.length > 4) box.firstChild.remove();
  setTimeout(kill, ms);
}
