// Background: keeps the connection to Marione, plays sounds on request and on the four global keys.
const ext = globalThis.browser ?? globalThis.chrome;
const ORIGIN = '__ORIGIN__';

const read = (keys) => ext.storage.local.get(keys);
const write = (items) => ext.storage.local.set(items);

async function call(path, body) {
  const { token } = await read('token');
  if (!token) throw new Error('not paired');
  const res = await fetch(ORIGIN + path, {
    method: body ? 'POST' : 'GET',
    headers: { Authorization: 'Bearer ' + token, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) await write({ token: null, config: null }); // revoked from the site
  if (!res.ok || data.ok === false) throw new Error(data.message || 'error ' + res.status);
  return data;
}

async function refresh() {
  const config = await call('/api/ext/config');
  await write({ config, fetchedAt: Date.now() });
  return config;
}

function badge(text, color) {
  const action = ext.action;
  if (!action) return;
  action.setBadgeBackgroundColor({ color });
  action.setBadgeText({ text });
  setTimeout(() => action.setBadgeText({ text: '' }), 2000);
}

async function play(id) {
  try {
    await call('/api/ext/play', { id });
    badge('♪', '#2f8f36');
    return { ok: true };
  } catch (e) {
    badge('!', '#d5321f');
    return { ok: false, message: String(e.message || e) };
  }
}

// The four commands (Ctrl+Shift+1…4, made global by the member if wanted) play the sounds that have Ctrl+1…4.
ext.commands.onCommand.addListener(async (name) => {
  const slot = Number(name.replace('sound-', ''));
  let { config } = await read('config');
  if (!config) { try { config = await refresh(); } catch { badge('!', '#d5321f'); return; } }
  const sound = config.sounds.find((s) => s.shortcut === 'Ctrl+' + slot);
  if (!sound) { badge('?', '#d29a0a'); return; }
  await play(sound.id);
  refresh().catch(() => {}); // pick up changes made on the site
});

ext.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.type === 'pair') {
      await write({ token: msg.token });
      try { const config = await refresh(); reply({ ok: true, name: config.me.name }); } catch (e) { reply({ ok: false, message: String(e.message || e) }); }
    } else if (msg.type === 'status') {
      const { token, config } = await read(['token', 'config']);
      reply({ paired: !!token, name: config ? config.me.name : null });
    } else if (msg.type === 'refresh') {
      try { reply({ ok: true, config: await refresh() }); } catch (e) { reply({ ok: false, message: String(e.message || e) }); }
    } else if (msg.type === 'play') {
      reply(await play(msg.id));
      const { fetchedAt } = await read('fetchedAt');
      if (!fetchedAt || Date.now() - fetchedAt > 60000) refresh().catch(() => {}); // the list may have changed
    } else if (msg.type === 'unpair') {
      await write({ token: null, config: null });
      reply({ ok: true });
    }
  })();
  return true; // the answer is sent later
});

// Keep the list fresh (a member may change sounds or keys on the site).
ext.runtime.onStartup?.addListener(() => { refresh().catch(() => {}); });
