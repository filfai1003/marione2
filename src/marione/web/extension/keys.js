// On every other site: pressing one of your Marione shortcuts (set on the soundboard page) plays that sound.
// Only a key combination that matches one of your shortcuts is acted on; nothing you type is read or kept.
const ext = globalThis.browser ?? globalThis.chrome;

const NAMED = {
  ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', Insert: 'Insert', Home: 'Home', End: 'End',
  PageUp: 'PageUp', PageDown: 'PageDown', NumpadAdd: 'NumAdd', NumpadSubtract: 'NumSubtract', NumpadMultiply: 'NumMultiply',
  NumpadDivide: 'NumDivide', NumpadDecimal: 'NumDecimal',
};

// Same naming as the Marione page (js/shortcuts.js): "Ctrl+Alt+K", "Alt+1", "F5", "Num3".
function comboOf(e) {
  if (e.metaKey || e.isComposing) return null;
  const c = e.code || '';
  let m, key = null;
  if ((m = /^Key([A-Z])$/.exec(c))) key = m[1];
  else if ((m = /^Digit([0-9])$/.exec(c))) key = m[1];
  else if (/^F([1-9]|1[0-2])$/.test(c)) key = c;
  else if ((m = /^Numpad([0-9])$/.exec(c))) key = 'Num' + m[1];
  else key = NAMED[c] || null;
  if (!key) return null;
  return [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift', key].filter(Boolean).join('+');
}

let sounds = {}; // combination -> sound id
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
