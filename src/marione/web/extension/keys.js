// On every other site: Ctrl+1 … Ctrl+9 and Ctrl+0 play the first ten sounds of your Marione soundboard list.
// Only those keys are acted on; nothing you type is read or kept.
const ext = globalThis.browser ?? globalThis.chrome;

// Same as the Marione page (js/shortcuts.js): "Ctrl+1" for Ctrl + a digit, otherwise null.
function comboOf(e) {
  if (e.metaKey || e.altKey || e.shiftKey || !e.ctrlKey || e.isComposing) return null;
  const m = /^(?:Digit|Numpad)([0-9])$/.exec(e.code || '');
  return m ? 'Ctrl+' + m[1] : null;
}

let sounds = {}; // "Ctrl+1" -> sound id (the server decides which sound has which key)
const load = (config) => {
  sounds = {};
  for (const s of (config && config.sounds) || []) if (s.shortcut) sounds[s.shortcut] = s.id;
};
ext.storage.local.get('config').then((r) => load(r.config));
ext.storage.onChanged.addListener((changes) => { if (changes.config) load(changes.config.newValue); });

const typing = (el) => el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

window.addEventListener('keydown', (e) => {
  if (e.repeat || typing(e.target)) return;
  const combo = comboOf(e);
  const id = combo && sounds[combo];
  if (!id) return;
  e.preventDefault();
  e.stopPropagation();
  ext.runtime.sendMessage({ type: 'play', id });
}, true);
