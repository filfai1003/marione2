// Keyboard shortcuts for soundboard sounds: one key combination per sound, saved per member.
// Pressing the combination on any page plays the sound in the member's voice channel.
import { h } from './util.js';
import { store } from './store.js';
import { post } from './api.js';
import { handleError, refreshState } from './data.js';
import { toast } from './toast.js';
import { t } from './i18n.js';
import { btn, modal } from './ui.js';

const NAMED = {
  ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', Insert: 'Insert', Home: 'Home', End: 'End',
  PageUp: 'PageUp', PageDown: 'PageDown', NumpadAdd: 'NumAdd', NumpadSubtract: 'NumSubtract', NumpadMultiply: 'NumMultiply',
  NumpadDivide: 'NumDivide', NumpadDecimal: 'NumDecimal',
};

/** "Ctrl+Alt+K" for a keydown event, or null if the key cannot be a shortcut. Uses the physical key
 *  (`code`), so Alt+1 is Alt+1 on every keyboard layout. The server accepts the same names. */
export function comboOf(e) {
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

const typing = (el) => el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

let installed = false;
/** Listen for the saved combinations on the whole page (once). */
export function installShortcuts() {
  if (installed) return;
  installed = true;
  window.addEventListener('keydown', (e) => {
    const st = store.state;
    if (e.repeat || store.view !== 'app' || !st || !st.modules.soundboard) return;
    if (typing(e.target) || document.querySelector('dialog[open]')) return;
    const combo = comboOf(e);
    const sound = combo && st.sounds.find((s) => s.shortcut === combo);
    if (!sound) return;
    e.preventDefault();
    post('/api/soundboard/play', { id: sound.id })
      .then(() => toast((sound.emoji || '🔊') + ' ' + sound.name))
      .catch(handleError);
  });
}

/** The "press the keys you want" dialog for one sound. */
export function shortcutModal(sound) {
  let combo = sound.shortcut || null;
  const shown = h('kbd', { class: 'kbd-big', 'aria-live': 'polite' });
  const draw = () => { shown.textContent = combo || t('board.shortcutNone'); shown.classList.toggle('empty', !combo); };
  draw();
  const save = async (key, close, b) => {
    b.disabled = true;
    try {
      await post('/api/soundboard/shortcut', { id: sound.id, key });
      toast(key ? t('board.shortcutSaved', { key }) : t('board.shortcutRemoved'));
      await refreshState();
      close();
    } catch (e) { handleError(e); } finally { b.disabled = false; }
  };
  const body = h('div', { class: 'stack' }, h('p', null, t('board.shortcutHint')), shown, h('p', { class: 'muted small' }, t('board.shortcutTip')));
  const { dlg } = modal(t('board.shortcutTitle', { name: sound.name }), body, (close) => [
    sound.shortcut ? btn(t('board.shortcutClear'), 'ghost', { onclick: (e) => save(null, close, e.currentTarget) }) : null,
    btn(t('common.cancel'), 'ghost', { onclick: close }),
    btn(t('common.save'), 'primary', { onclick: (e) => { if (combo) save(combo, close, e.currentTarget); else shown.focus(); } }),
  ]);
  dlg.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' || e.key === 'Tab') return; // Esc closes the dialog, Tab moves between buttons
    const c = comboOf(e);
    if (c) { e.preventDefault(); combo = c; draw(); }
  });
}
