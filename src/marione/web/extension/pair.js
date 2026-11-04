// Runs on the Marione site only: lets the page hand the extension its token (one click, no copy and paste)
// and tell whether the extension is installed and connected.
const ext = globalThis.browser ?? globalThis.chrome;

document.documentElement.dataset.marioneExt = '1';

window.addEventListener('message', async (event) => {
  if (event.source !== window || event.origin !== location.origin || !event.data) return;
  const { type } = event.data;
  if (type === 'marione-pair' && typeof event.data.token === 'string') {
    const result = await ext.runtime.sendMessage({ type: 'pair', token: event.data.token });
    window.postMessage({ type: 'marione-ext-paired', ...result }, location.origin);
  } else if (type === 'marione-ext-ping') {
    const status = await ext.runtime.sendMessage({ type: 'status' });
    window.postMessage({ type: 'marione-ext-pong', ...status }, location.origin);
  } else if (type === 'marione-unpair') {
    await ext.runtime.sendMessage({ type: 'unpair' });
    window.postMessage({ type: 'marione-ext-pong', paired: false, name: null }, location.origin);
  } else if (type === 'marione-refresh') {
    await ext.runtime.sendMessage({ type: 'refresh' });
  }
});
