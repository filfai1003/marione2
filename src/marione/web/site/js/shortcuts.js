// Keyboard shortcuts for the soundboard. They need no setup: the first ten sounds of the list
// (favourites first, then by name) answer to Ctrl+1 … Ctrl+9 and Ctrl+0. The server says which sound
// has which key (`shortcut` on each sound), so the keys follow the list when it changes.
// Pressing one on any page plays the sound in the member's voice channel.
import { store } from './store.js';
import { post } from './api.js';
import { handleError } from './data.js';
import { toast } from './toast.js';

/** "Ctrl+1" for a keydown event, or null if it is not Ctrl + a digit. Uses the physical key
 *  (`code`), so it is the same on every keyboard layout. (The extension has the same function.) */
export function comboOf(e) {
  if (e.metaKey || e.altKey || e.shiftKey || !e.ctrlKey || e.isComposing) return null;
  const m = /^(?:Digit|Numpad)([0-9])$/.exec(e.code || '');
  return m ? 'Ctrl+' + m[1] : null;
}

const typing = (el) => el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

let installed = false;
/** Listen for the keys on the whole page (once). */
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
