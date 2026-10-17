// The house games against Marione's bank: the slot, roulette, blackjack and sette e mezzo.
// One engine object is one round; when the round is over, sending its first action again starts
// the next one (the server does it). Animations are driven by timestamps kept in ctx.local, so a
// re-render in the middle of a spin (a poll, a bet change) continues it seamlessly.
import { h, fill, fmt } from '../util.js';
import { card, icon } from '../art.js';
import { local } from './common.js';

const tr = local({
  en: {
    bet: 'Bet', win: 'Win', lastWin: 'Last win', lines: 'Lines', less: 'Lower the bet', more: 'Raise the bet', max: 'Max',
    spin: 'SPIN', spinning: 'Spinning…', spinAgain: 'SPIN', slotTitle: 'La Slot di Marione', bigWin: 'BIG WIN!',
    lineWin: 'Line {n}', scatterWin: '{n} Marioncelli', noWin: 'No luck this time', youWon: 'You won {n}', youLost: 'You lost {n}',
    pushed: 'Bet returned', paytable: 'Paytable', paytableNote: 'Pays are multiples of the total bet. 10 fixed lines, left to right.',
    wildNote: 'Marione is wild: he stands in for every symbol except the coin.', scatterNote: 'Marioncelli pay anywhere on the reels:',
    paylines: 'Paylines', place: 'Place your bets', chip: 'Chip value', betType: 'Bet type', straight: 'Number', split: 'Split',
    street: 'Street', corner: 'Corner', line: 'Six line', hintStraight: 'Tap a number to bet on it (35 to 1).',
    hintSplit: 'Tap two neighbouring numbers (17 to 1).', hintStreet: 'Tap a number to bet on its row of three (11 to 1). For 0-1-2 or 0-2-3, tap 0 first.',
    hintCorner: 'Tap two numbers of the square of four (8 to 1).', hintLine: 'Tap a number: its row and the next one, six numbers (5 to 1).',
    pickPartner: 'Now tap the second number.', totalBet: 'On the table', limit: 'limit {n}', final: 'Bets are final once placed.',
    spinWheel: 'Spin the wheel', repeat: 'Repeat bets', newRound: 'Tap the cloth to start a new round.', result: 'Result',
    red: 'Red', black: 'Black', even: 'Even', odd: 'Odd', low: '1–18', high: '19–36', dozen: '{n}ª 12', column: '2 to 1',
    zero: 'Zero', yourBets: 'Your bets', betOn: 'Bet {amount} on {what}', noBets: 'No bets yet.', wheel: 'Roulette wheel',
    dealer: 'Dealer', you: 'You', hand: 'Hand {n}', hit: 'Hit', stand: 'Stand', double: 'Double', splitH: 'Split', deal: 'Deal',
    dealAgain: 'Deal again', bjRule: 'Blackjack pays 3 to 2 · Dealer stands on 17', r_win: 'Win', r_lose: 'Lose', r_push: 'Push',
    r_bust: 'Bust', r_blackjack: 'Blackjack!', doubled: 'Doubled', shoe: 'Shoe: {n} cards', bjPick: 'Choose your bet and deal.',
    bank: 'The bank (Marione)', card: 'Card', stay: 'Stand', play: 'Play', playAgain: 'Play again', sem: 'Sette e mezzo',
    semRule: 'Figures count ½ · the King of coins is wild · over 7½ is bust', s_win: 'You win!', s_reale: 'Sette e mezzo reale!',
    s_lose: 'The bank wins', s_bust: 'Bust!', covered: 'only you see it', total: 'Total', payout: 'Payout', semPick: 'Choose your bet and take the first card.',
    yourMove: 'Your move', cost: '+{n}',
  },
  it: {
    bet: 'Puntata', win: 'Vincita', lastWin: 'Ultima vincita', lines: 'Linee', less: 'Abbassa la puntata', more: 'Alza la puntata', max: 'Max',
    spin: 'GIRA', spinning: 'Gira…', spinAgain: 'GIRA', slotTitle: 'La Slot di Marione', bigWin: 'SUPER VINCITA!',
    lineWin: 'Linea {n}', scatterWin: '{n} Marioncelli', noWin: 'Niente stavolta', youWon: 'Hai vinto {n}', youLost: 'Hai perso {n}',
    pushed: 'Puntata restituita', paytable: 'Tabella premi', paytableNote: 'Le vincite sono multipli della puntata totale. 10 linee fisse, da sinistra.',
    wildNote: 'Marione è il jolly: sostituisce ogni simbolo tranne la moneta.', scatterNote: 'I Marioncelli pagano ovunque sui rulli:',
    paylines: 'Linee di pagamento', place: 'Fate il vostro gioco', chip: 'Valore fiche', betType: 'Tipo di puntata', straight: 'Pieno', split: 'Cavallo',
    street: 'Terzina', corner: 'Carré', line: 'Sestina', hintStraight: 'Tocca un numero per puntarci (35 a 1).',
    hintSplit: 'Tocca due numeri vicini (17 a 1).', hintStreet: 'Tocca un numero per la sua fila di tre (11 a 1). Per 0-1-2 o 0-2-3 tocca prima lo 0.',
    hintCorner: 'Tocca due numeri del quadrato di quattro (8 a 1).', hintLine: 'Tocca un numero: la sua fila e la successiva, sei numeri (5 a 1).',
    pickPartner: 'Ora tocca il secondo numero.', totalBet: 'Sul tavolo', limit: 'limite {n}', final: 'Le puntate piazzate non si ritirano.',
    spinWheel: 'Gira la ruota', repeat: 'Ripeti puntate', newRound: 'Tocca il tappeto per un nuovo giro.', result: 'Risultato',
    red: 'Rosso', black: 'Nero', even: 'Pari', odd: 'Dispari', low: '1–18', high: '19–36', dozen: '{n}ª 12', column: '2 a 1',
    zero: 'Zero', yourBets: 'Le tue puntate', betOn: 'Punta {amount} su {what}', noBets: 'Nessuna puntata.', wheel: 'Ruota della roulette',
    dealer: 'Banco', you: 'Tu', hand: 'Mano {n}', hit: 'Carta', stand: 'Stai', double: 'Raddoppia', splitH: 'Dividi', deal: 'Distribuisci',
    dealAgain: 'Nuova mano', bjRule: 'Il blackjack paga 3 a 2 · Il banco sta a 17', r_win: 'Vinta', r_lose: 'Persa', r_push: 'Pari',
    r_bust: 'Sballato', r_blackjack: 'Blackjack!', doubled: 'Raddoppiata', shoe: 'Sabot: {n} carte', bjPick: 'Scegli la puntata e distribuisci.',
    bank: 'Il banco (Marione)', card: 'Carta', stay: 'Sto', play: 'Gioca', playAgain: 'Gioca ancora', sem: 'Sette e mezzo',
    semRule: 'Le figure valgono ½ · il re di denari è la matta · oltre 7½ si sballa', s_win: 'Hai vinto!', s_reale: 'Sette e mezzo reale!',
    s_lose: 'Vince il banco', s_bust: 'Sballato!', covered: 'la vedi solo tu', total: 'Totale', payout: 'Vincita', semPick: 'Scegli la puntata e prendi la prima carta.',
    yourMove: 'Tocca a te', cost: '+{n}',
  },
  fr: {
    bet: 'Mise', win: 'Gain', lastWin: 'Dernier gain', lines: 'Lignes', less: 'Baisser la mise', more: 'Augmenter la mise', max: 'Max',
    spin: 'LANCER', spinning: 'Ça tourne…', spinAgain: 'LANCER', slotTitle: 'La Slot di Marione', bigWin: 'GROS GAIN !',
    lineWin: 'Ligne {n}', scatterWin: '{n} Marioncelli', noWin: 'Pas de chance cette fois', youWon: 'Vous gagnez {n}', youLost: 'Vous perdez {n}',
    pushed: 'Mise rendue', paytable: 'Table des gains', paytableNote: 'Les gains sont des multiples de la mise totale. 10 lignes fixes, de gauche à droite.',
    wildNote: 'Marione est joker : il remplace tous les symboles sauf la pièce.', scatterNote: 'Les Marioncelli paient n’importe où :',
    paylines: 'Lignes de paiement', place: 'Faites vos jeux', chip: 'Valeur du jeton', betType: 'Type de mise', straight: 'Plein', split: 'Cheval',
    street: 'Transversale', corner: 'Carré', line: 'Sixain', hintStraight: 'Touchez un numéro pour miser dessus (35 contre 1).',
    hintSplit: 'Touchez deux numéros voisins (17 contre 1).', hintStreet: 'Touchez un numéro pour sa rangée de trois (11 contre 1). Pour 0-1-2 ou 0-2-3, touchez d’abord le 0.',
    hintCorner: 'Touchez deux numéros du carré de quatre (8 contre 1).', hintLine: 'Touchez un numéro : sa rangée et la suivante, six numéros (5 contre 1).',
    pickPartner: 'Touchez maintenant le second numéro.', totalBet: 'Sur le tapis', limit: 'limite {n}', final: 'Les mises posées sont définitives.',
    spinWheel: 'Lancer la roue', repeat: 'Rejouer les mises', newRound: 'Touchez le tapis pour un nouveau tour.', result: 'Résultat',
    red: 'Rouge', black: 'Noir', even: 'Pair', odd: 'Impair', low: '1–18', high: '19–36', dozen: '{n}e 12', column: '2 contre 1',
    zero: 'Zéro', yourBets: 'Vos mises', betOn: 'Miser {amount} sur {what}', noBets: 'Aucune mise.', wheel: 'Roue de la roulette',
    dealer: 'Croupier', you: 'Vous', hand: 'Main {n}', hit: 'Carte', stand: 'Rester', double: 'Doubler', splitH: 'Séparer', deal: 'Distribuer',
    dealAgain: 'Nouvelle main', bjRule: 'Le blackjack paie 3 contre 2 · Le croupier reste à 17', r_win: 'Gagné', r_lose: 'Perdu', r_push: 'Égalité',
    r_bust: 'Brûlé', r_blackjack: 'Blackjack !', doubled: 'Doublée', shoe: 'Sabot : {n} cartes', bjPick: 'Choisissez votre mise et distribuez.',
    bank: 'La banque (Marione)', card: 'Carte', stay: 'Rester', play: 'Jouer', playAgain: 'Rejouer', sem: 'Sette e mezzo',
    semRule: 'Les figures valent ½ · le roi de deniers est joker · au-delà de 7½ on saute', s_win: 'Gagné !', s_reale: 'Sette e mezzo reale !',
    s_lose: 'La banque gagne', s_bust: 'Sauté !', covered: 'vous seul la voyez', total: 'Total', payout: 'Gain', semPick: 'Choisissez votre mise et prenez la première carte.',
    yourMove: 'À vous', cost: '+{n}',
  },
});

const coins = (n) => fmt(n) + ' 🪙';
const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let timer = null;

export function destroy() { clearTimeout(timer); timer = null; }

/** Re-renders the board later (end of an animation), with the latest table. */
function later(el, ctx, ms) {
  clearTimeout(timer);
  timer = setTimeout(() => { if (el.isConnected && ctx.table) render(el, ctx.table, ctx); }, Math.max(0, ms) + 30);
}

// UI state per table, kept here as well as in ctx.local: it must survive the page rebuilding the
// table view (it does so on every store refresh), or a spin would lose its animation.
const STATE = new Map();

export function render(el, tb, ctx0) {
  const base = ctx0._base || ctx0;
  if (!STATE.has(tb.id)) STATE.set(tb.id, base.local || {});
  const ctx = Object.create(base, { local: { value: STATE.get(tb.id) }, _base: { value: base } });
  const focusKey = document.activeElement && el.contains(document.activeElement) ? document.activeElement.dataset.k : null;
  clearTimeout(timer);
  const draw = { slot: slotView, roulette: rouletteView, blackjack: blackjackView, settemezzo: semView }[tb.game];
  fill(el, h('div', { class: 'cas cas-' + tb.game }, draw ? draw(el, tb, ctx) : null));
  if (focusKey) { const f = el.querySelector(`[data-k="${focusKey}"]`); if (f && !f.disabled) f.focus(); }
}

// ======================================================================================
// shared bits
// ======================================================================================
const SERIES = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000];
const baseBet = (tb) => Math.max(1, tb.stake || 10);
const clamp = (v, max) => Math.max(1, Math.min(max, Math.round(v)));

function getBet(tb, ctx, max) {
  if (ctx.local.bet == null) ctx.local.bet = baseBet(tb);
  ctx.local.bet = clamp(ctx.local.bet, max);
  return ctx.local.bet;
}

/** − value + and a row of quick chips. Changes re-render the board (focus is restored). */
function betPicker(el, tb, ctx, max, disabled) {
  const v = getBet(tb, ctx, max);
  const set = (n) => { ctx.local.bet = clamp(n, max); render(el, ctx.table, ctx); };
  const down = [...SERIES].reverse().find((s) => s < v) || 1;
  const up = SERIES.find((s) => s > v) || max;
  const base = baseBet(tb);
  const quick = [...new Set([base, base * 2, base * 5, base * 10, max].map((n) => clamp(n, max)))].sort((a, b) => a - b);
  return h('div', { class: 'cas-bet' },
    h('span', { class: 'cas-bet-lbl' }, tr('bet')),
    h('div', { class: 'cas-stepper' },
      h('button', { type: 'button', class: 'cas-step', 'aria-label': tr('less'), 'data-k': 'bet-down', disabled: disabled || v <= 1, onclick: () => set(down) }, '−'),
      h('output', { class: 'cas-bet-val', 'aria-live': 'polite' }, coins(v)),
      h('button', { type: 'button', class: 'cas-step', 'aria-label': tr('more'), 'data-k': 'bet-up', disabled: disabled || v >= max, onclick: () => set(up) }, '+')),
    h('div', { class: 'cas-quick' }, quick.map((n) => h('button', {
      type: 'button', class: 'cas-qchip' + (n === v ? ' on' : ''), 'aria-pressed': n === v ? 'true' : 'false', 'data-k': 'q' + n, disabled,
      onclick: () => set(n),
    }, n === max && n !== base ? tr('max') : fmt(n)))));
}

/** The outcome of a round: a pill with the net result. */
function outcome(net, gross, extra) {
  const cls = gross > 0 && net > 0 ? 'win' : net < 0 ? 'lose' : 'push';
  const text = net > 0 ? tr('youWon', { n: coins(net) }) : net < 0 && gross > 0 ? `${tr('win')} ${coins(gross)} · −${fmt(-net)}`
    : net < 0 ? tr('youLost', { n: coins(-net) }) : tr('pushed');
  return h('div', { class: 'cas-outcome ' + cls, role: 'status' }, extra ? h('strong', null, extra) : null, h('span', null, text));
}

function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

// ======================================================================================
// slot
// ======================================================================================
const SYMS = ['marione', 'spaghetti', 'pizza', 'mandolino', 'vespa', 'moka', 'pomodoro', 'basilico', 'coin'];
const LINE_COLORS = ['#e9b420', '#e64f3f', '#52ac54', '#2c9ad8', '#c45ad6', '#ff8a1f', '#1ABC9C', '#f06292', '#9ccc65', '#ffd54f'];
const REEL_MS = (r) => 1000 + r * 320;

function slotView(el, tb, ctx) {
  const st = tb.state;
  const L = ctx.local;
  const max = (tb.legal[0] && tb.legal[0].max) || st.maxBet;
  // a new result arrived after our own spin: start the reels
  if (st.spun && L.slotWant) { L.slotWant = false; L.slotAnim = { round: tb.round, t0: performance.now() }; }
  const anim = L.slotAnim && L.slotAnim.round === tb.round && st.spun && !reduced() ? L.slotAnim : null;
  const elapsed = anim ? performance.now() - anim.t0 : Infinity;
  const total = REEL_MS(4);
  const spinning = elapsed < total;
  if (spinning) later(el, ctx, total - elapsed);
  const showWin = st.spun && !spinning;

  const winCells = new Set();
  const lineOf = new Map();
  if (showWin) {
    st.lines.forEach((ln) => ln.cells.forEach(([r, row]) => { winCells.add(r + ':' + row); lineOf.set(r + ':' + row, ln.line); }));
    st.scatter.cells.forEach(([r, row]) => winCells.add(r + ':' + row));
  }

  const reels = st.grid.map((col, r) => {
    const cell = (sym, row, fin) => h('div', {
      class: 'cas-cell' + (fin && winCells.has(r + ':' + row) ? ' hit' : '') + (fin && showWin && winCells.size && !winCells.has(r + ':' + row) ? ' dim' : ''),
      style: fin && lineOf.has(r + ':' + row) ? { '--lc': LINE_COLORS[lineOf.get(r + ':' + row)] } : null,
    }, icon('slot_' + sym, 96, sym));
    if (anim && elapsed < REEL_MS(r)) {
      const rand = rng(tb.round * 97 + r * 13 + 7);
      const n = 14 + r * 4;
      const fillers = Array.from({ length: n }, () => SYMS[Math.floor(rand() * SYMS.length)]);
      const strip = [fillers[0], ...col, ...fillers.slice(1)];
      const cells = strip.length;
      return h('div', { class: 'cas-reel' },
        h('div', {
          class: 'cas-strip spin', style: {
            '--y0': `${-((cells - 3) / cells) * 100}%`, '--y1': `${-(1 / cells) * 100}%`,
            animationDuration: REEL_MS(r) + 'ms', animationDelay: -elapsed + 'ms',
          },
        }, strip.map((s, i) => cell(s, i - 1, false))));
    }
    return h('div', { class: 'cas-reel' + (anim && elapsed < REEL_MS(r) + 400 ? ' landed' : '') },
      h('div', { class: 'cas-strip' }, col.map((s, row) => cell(s, row, true))));
  });

  const paths = showWin ? st.lines.map((ln, i) => svg('polyline', {
    points: st.paylines[ln.line].map((row, r) => `${r * 100 + 50},${row * 100 + 50}`).join(' '),
    stroke: LINE_COLORS[ln.line], pathLength: 1, style: `--d:${i * 120}ms`,
  })) : [];
  const overlay = svg('svg', { class: 'cas-paylines', viewBox: '0 0 500 300', preserveAspectRatio: 'none', 'aria-hidden': 'true' }, paths);

  const bet = getBet(tb, ctx, max);
  const big = showWin && st.win >= st.bet * 10;
  const lights = (n) => h('div', { class: 'cas-lights' + (showWin && st.win ? ' party' : '') + (spinning ? ' chase' : ''), 'aria-hidden': 'true' },
    Array.from({ length: n }, (_, i) => h('span', { style: { '--i': i } })));

  const spinBtn = h('button', {
    type: 'button', class: 'cas-spin', 'data-k': 'spin', disabled: spinning || tb.you == null,
    onclick: async (e) => { L.slotWant = true; await ctx.act({ type: 'spin', amount: bet }, e.currentTarget); L.slotWant = false; },
  }, h('span', null, spinning ? tr('spinning') : tr('spin')), h('small', null, coins(bet)));

  const wins = showWin && (st.lines.length || st.scatter.pay)
    ? h('ul', { class: 'cas-wins' },
      st.lines.map((ln) => h('li', { style: { '--lc': LINE_COLORS[ln.line] } }, h('span', { class: 'cas-dot' }),
        tr('lineWin', { n: ln.line + 1 }) + ' · ' + ln.count + '×', icon('slot_' + ln.symbol, 26, ln.symbol), h('b', null, '+' + fmt(ln.pay)))),
      st.scatter.pay ? h('li', null, icon('slot_coin', 26, 'coin'), tr('scatterWin', { n: st.scatter.count }), h('b', null, '+' + fmt(st.scatter.pay))) : null)
    : null;

  return [
    h('div', { class: 'cas-cabinet' + (big ? ' big' : '') },
      h('div', { class: 'cas-marquee' }, lights(14),
        h('div', { class: 'cas-mq-title' }, icon('slot_marione', 46), h('strong', null, tr('slotTitle')), icon('slot_coin', 34))),
      h('div', { class: 'cas-window' }, h('div', { class: 'cas-reels' }, reels, overlay),
        big ? h('div', { class: 'cas-bigwin', role: 'status' }, tr('bigWin')) : null),
      h('div', { class: 'cas-panel' },
        h('div', { class: 'cas-led' }, h('small', null, tr('bet')), h('b', null, fmt(st.spun ? st.bet : bet))),
        h('div', { class: 'cas-led' }, h('small', null, tr('lines')), h('b', null, '10')),
        h('div', { class: 'cas-led win' + (showWin && st.win ? ' lit' : '') }, h('small', null, tr('win')), h('b', null, showWin ? fmt(st.win) : spinning ? '…' : '0'))),
      h('div', { class: 'cas-controls' }, betPicker(el, tb, ctx, max, spinning), spinBtn)),
    showWin ? (st.win ? outcome(st.win - st.bet, st.win, null) : h('p', { class: 'cas-outcome lose', role: 'status' }, tr('noWin'), ' · −' + coins(st.bet))) : null,
    wins,
    slotPaytable(st, bet),
  ];
}

function slotPaytable(st, bet) {
  const rows = Object.entries(st.paytable).map(([sym, pays]) => h('tr', null,
    h('th', { scope: 'row' }, icon('slot_' + sym, 40, sym)),
    ['3', '4', '5'].map((k) => h('td', null, h('b', null, '×' + fmtMult(pays[k])), h('small', null, fmt(Math.floor(bet * pays[k])))))));
  return h('details', { class: 'cas-paytable' },
    h('summary', null, icon('slot_spaghetti', 28), tr('paytable')),
    h('div', { class: 'cas-pt-body' },
      h('p', { class: 'cas-pt-note' }, tr('paytableNote')),
      h('table', null, h('thead', null, h('tr', null, h('th', null), ['3', '4', '5'].map((k) => h('th', { scope: 'col' }, k + '×')))), h('tbody', null, rows)),
      h('p', { class: 'cas-pt-note' }, icon('slot_marione', 34), tr('wildNote')),
      h('p', { class: 'cas-pt-note' }, icon('slot_coin', 34), tr('scatterNote') + ' ' +
        Object.entries(st.scatterPays).map(([k, v]) => `${k}× → ×${v}`).join(' · ')),
      h('h4', null, tr('paylines')),
      h('div', { class: 'cas-pl-grid' }, st.paylines.map((pl, i) => h('div', { class: 'cas-pl', style: { '--lc': LINE_COLORS[i] } },
        h('small', null, String(i + 1)),
        h('div', { class: 'cas-pl-cells' }, [0, 1, 2].map((row) => [0, 1, 2, 3, 4].map((r) => h('span', { class: pl[r] === row ? 'on' : '' })))))))));
}
const fmtMult = (m) => (Number.isInteger(m) ? String(m) : String(m).replace('.', ','));

function svg(tag, attrs, ...kids) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) e.setAttribute(k, String(v));
  for (const k of kids.flat(Infinity)) if (k != null) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}

// ======================================================================================
// roulette
// ======================================================================================
const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const numColor = (n) => (n === 0 ? 'green' : RED.has(n) ? 'red' : 'black');
const WHEEL_MS = 5200;
const CHIPS = [1, 5, 10, 25, 100, 500, 1000, 5000, 25000];
const KINDS = ['straight', 'split', 'street', 'corner', 'line'];

const SETS = (() => {
  const split = [[0, 1], [0, 2], [0, 3]], street = [[0, 1, 2], [0, 2, 3]], corner = [[0, 1, 2, 3]], line = [];
  for (let n = 1; n <= 36; n++) {
    if (n % 3 !== 0) split.push([n, n + 1]);
    if (n <= 33) split.push([n, n + 3]);
  }
  for (let n = 1; n <= 34; n += 3) street.push([n, n + 1, n + 2]);
  for (let n = 1; n <= 32; n++) if (n % 3 !== 0) corner.push([n, n + 1, n + 3, n + 4]);
  for (let n = 1; n <= 31; n += 3) line.push([n, n + 1, n + 2, n + 3, n + 4, n + 5]);
  return { split, street, corner, line };
})();

/** Grid position of a number on the cloth: column 0 is the zero, rows 0 (top: 3, 6...) to 2. */
const cellPos = (n) => (n === 0 ? [0, 1] : [Math.ceil(n / 3), 2 - ((n - 1) % 3)]);

function betLabel(b) {
  const nums = b.numbers || [];
  if (b.bet === 'straight') return String(b.target);
  if (b.bet === 'dozen') return tr('dozen', { n: b.target });
  if (b.bet === 'column') return tr('column') + ' (' + b.target + ')';
  if (['red', 'black', 'even', 'odd', 'low', 'high'].includes(b.bet)) return tr(b.bet);
  return tr(b.bet) + ' ' + nums.join('-');
}
const betKey = (kind, target) => kind + ':' + (Array.isArray(target) ? target.join('-') : target == null ? '' : target);

function rouletteView(el, tb, ctx) {
  const st = tb.state;
  const L = ctx.local;
  const done = st.phase === 'done';
  const over = tb.status === 'over';
  if (done && L.rlWant) { L.rlWant = false; L.rlAnim = { round: tb.round, t0: performance.now(), from: L.rlRest || 0 }; }
  const anim = L.rlAnim && L.rlAnim.round === tb.round && done && !reduced() ? L.rlAnim : null;
  const elapsed = anim ? performance.now() - anim.t0 : Infinity;
  const spinning = elapsed < WHEEL_MS;
  if (spinning) later(el, ctx, WHEEL_MS - elapsed);
  const reveal = done && !spinning;
  if (!L.rlKind) L.rlKind = 'straight';
  const room = st.maxTotal - (over ? 0 : st.total);
  const chips = CHIPS.filter((c) => c <= st.maxTotal);
  if (L.chip == null) L.chip = [...chips].reverse().find((c) => c <= baseBet(tb)) || chips[0];
  if (L.chip > st.maxTotal) L.chip = chips[chips.length - 1];
  const canBet = tb.you != null && !spinning && (over || room >= 1);
  const amount = () => Math.min(L.chip, over ? st.maxTotal : room);
  const redraw = () => render(el, ctx.table, ctx);

  async function place(kind, target, btn) {
    if (!canBet) return;
    if (over) L.rlLast = st.bets.map((b) => ({ bet: b.bet, target: b.target, amount: b.amount }));
    L.anchor = null;
    const action = { type: 'bet', bet: kind, amount: amount() };
    if (target != null) action.target = target;
    await ctx.act(action, btn);
  }

  // where the chips are: aggregated per bet
  const agg = new Map(); // wins are shown only once the wheel stops
  for (const b of st.bets) {
    const k = betKey(b.bet, b.target);
    const a = agg.get(k) || { ...b, amount: 0, win: 0 };
    a.amount += b.amount; a.win += b.win || 0;
    agg.set(k, a);
  }
  const chipEl = (a) => h('span', {
    class: 'cas-chip on-cloth' + (reveal ? (a.win ? ' won' : ' lost') : ''), 'aria-hidden': 'true',
  }, abbrevChip(a.amount));
  const chipFor = (k) => (agg.has(k) ? chipEl(agg.get(k)) : null);

  // number clicks with the bet type picker
  const kind = L.rlKind;
  const anchor = L.anchor;
  const partners = new Set();
  if (anchor != null) for (const s of SETS[kind] || []) if (s.includes(anchor)) s.forEach((n) => n !== anchor && partners.add(n));
  function clickNumber(n, btn) {
    if (kind === 'straight') return place('straight', n, btn);
    const sets = SETS[kind];
    if (anchor != null && n !== anchor) {
      const s = sets.find((x) => x.includes(anchor) && x.includes(n));
      if (s) return place(kind, s, btn);
    }
    if (anchor === n) { L.anchor = null; return redraw(); }
    if ((kind === 'street' || kind === 'line') && n !== 0) {
      const row = n - ((n - 1) % 3);
      const start = kind === 'line' ? Math.min(row, 31) : row;
      return place(kind, sets.find((x) => x[0] === start && x.length === (kind === 'line' ? 6 : 3) && !x.includes(0)), btn);
    }
    L.anchor = n;
    return redraw();
  }

  const winN = reveal ? st.result : null;
  const numBtn = (n) => {
    const [c, r] = cellPos(n);
    return h('button', {
      type: 'button', class: `cas-num ${numColor(n)}` + (n === winN ? ' winner' : '') + (n === anchor ? ' anchor' : '') + (partners.has(n) ? ' partner' : ''),
      style: n === 0 ? { '--gc': '1', '--gr': '1 / span 3', '--mc': '1 / span 3', '--mr': '1' }
        : { '--gc': String(c + 1), '--gr': String(r + 1), '--mc': String(((n - 1) % 3) + 1), '--mr': String(c + 1) },
      disabled: !canBet, 'data-k': 'n' + n, 'aria-label': tr('betOn', { amount: fmt(amount()), what: n }),
      onclick: (e) => clickNumber(n, e.currentTarget),
      onmouseenter: () => hover(n), onmouseleave: () => hover(null), onfocus: () => hover(n), onblur: () => hover(null),
    }, h('span', null, String(n)), chipFor(betKey('straight', n)));
  };
  // highlights what a click would cover
  let cloth = null;
  function hover(n) {
    if (!cloth) return;
    cloth.querySelectorAll('.cov').forEach((x) => x.classList.remove('cov'));
    if (n == null || !canBet) return;
    let cover = [n];
    if (kind === 'street' || kind === 'line') {
      if (n !== 0) { const row = n - ((n - 1) % 3); const start = kind === 'line' ? Math.min(row, 31) : row; cover = Array.from({ length: kind === 'line' ? 6 : 3 }, (_, i) => start + i); }
    }
    if (anchor != null && (kind === 'split' || kind === 'corner' || kind === 'street')) {
      const s = SETS[kind].find((x) => x.includes(anchor) && x.includes(n));
      if (s) cover = s;
    }
    cover.forEach((m) => { const b = cloth.querySelector(`[data-k="n${m}"]`); if (b) b.classList.add('cov'); });
  }
  const outside = (k, target, label, cls, style) => h('button', {
    type: 'button', class: 'cas-out ' + (cls || ''), style, disabled: !canBet, 'data-k': 'o' + k + (target ?? ''),
    'aria-label': tr('betOn', { amount: fmt(amount()), what: label }),
    onclick: (e) => place(k, target ?? null, e.currentTarget),
    onmouseenter: () => hoverSet(st, k, target), onmouseleave: () => hover(null),
  }, h('span', null, label), chipFor(betKey(k, target ?? '')),
  reveal && isWinOutside(k, target, st.result) ? h('span', { class: 'cas-glow', 'aria-hidden': 'true' }) : null);
  function hoverSet(_, k, target) {
    if (!cloth || !canBet) return;
    cloth.querySelectorAll('.cov').forEach((x) => x.classList.remove('cov'));
    for (let n = 1; n <= 36; n++) if (isWinOutside(k, target, n)) { const b = cloth.querySelector(`[data-k="n${n}"]`); if (b) b.classList.add('cov'); }
  }

  // inside bets that sit between numbers: chips placed over the grid
  const between = [...agg.values()].filter((a) => ['split', 'street', 'corner', 'line'].includes(a.bet)).map((a) => {
    const pts = a.numbers.map(cellPos);
    const x = pts.reduce((s, p) => s + p[0], 0) / pts.length, y = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    const yy = a.bet === 'street' || a.bet === 'line' ? 3 : y; // streets and lines sit on the bottom edge
    // phones: the cloth stands upright (3 columns, zero on top)
    const mx = a.numbers.reduce((s, n) => s + (n === 0 ? 1 : (n - 1) % 3), 0) / a.numbers.length;
    const my = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const edge = a.bet === 'street' || a.bet === 'line';
    return h('span', { class: 'cas-float', style: {
      '--dx': ((x + 0.5) / 14 * 100) + '%', '--dy': (yy === 3 ? 100 : (yy + 0.5) / 3 * 100) + '%',
      '--mx': (edge ? 0 : (mx + 0.5) / 3 * 100) + '%', '--my': ((my + 0.5) / 14 * 100) + '%',
    } }, chipEl(a));
  });

  cloth = h('div', { class: 'cas-cloth' + (canBet ? '' : ' locked') },
    h('div', { class: 'cas-grid' },
      numBtn(0),
      Array.from({ length: 36 }, (_, i) => numBtn(i + 1)),
      [1, 2, 3].map((c) => outside('column', 4 - c, tr('column'), 'col', { '--gc': '14', '--gr': String(c), '--mc': String(4 - c), '--mr': '14' })),
      h('div', { class: 'cas-floats', 'aria-hidden': 'true' }, between)),
    h('div', { class: 'cas-dozens' }, [1, 2, 3].map((d) => outside('dozen', d, tr('dozen', { n: d })))),
    h('div', { class: 'cas-even' },
      outside('low', null, tr('low')), outside('even', null, tr('even')),
      outside('red', null, tr('red'), 'redb', null), outside('black', null, tr('black'), 'blackb', null),
      outside('odd', null, tr('odd')), outside('high', null, tr('high'))));

  // the wheel
  const idx = st.result != null ? st.wheel.indexOf(st.result) : -1;
  const seg = 360 / 37;
  let rest = L.rlRest || 0;
  let wheelStyle = { transform: `rotate(${rest}deg)` }, ballStyle = null, dropStyle = null;
  if (done && idx >= 0) {
    const target = -idx * seg;
    if (anim && spinning) {
      const from = anim.from;
      let to = target;
      while (to < from + 1440) to += 360;
      anim.to = to;
      wheelStyle = { '--w0': from + 'deg', '--w1': to + 'deg', animationDelay: -elapsed + 'ms', animationDuration: WHEEL_MS + 'ms' };
      ballStyle = { animationDelay: -elapsed + 'ms', animationDuration: WHEEL_MS + 'ms' };
      dropStyle = ballStyle;
      L.rlRest = ((to % 360) + 360) % 360;
    } else {
      L.rlRest = ((target % 360) + 360) % 360;
      wheelStyle = { transform: `rotate(${L.rlRest}deg)` };
    }
    rest = L.rlRest;
  }
  const wheel = h('div', { class: 'cas-wheel-wrap' },
    h('div', { class: 'cas-wheel', role: 'img', 'aria-label': tr('wheel') + (reveal ? ' · ' + st.result : '') },
      h('div', { class: 'cas-wheel-disc' + (anim && spinning ? ' spin' : ''), style: wheelStyle }, wheelSvg(st.wheel)),
      done && idx >= 0 ? h('div', { class: 'cas-ball-orbit' + (anim && spinning ? ' spin' : ''), style: ballStyle },
        h('div', { class: 'cas-ball-drop' + (anim && spinning ? ' spin' : ''), style: dropStyle }, h('span', { class: 'cas-ball' }))) : null,
      h('div', { class: 'cas-hub', 'aria-hidden': 'true' })),
    reveal ? h('div', { class: 'cas-result ' + st.color, role: 'status' }, h('small', null, tr('result')), h('b', null, String(st.result))) : null);

  // the side panel: chips, bet types, totals, buttons
  const chipRow = h('div', { class: 'cas-chips', role: 'group', 'aria-label': tr('chip') }, chips.map((c, i) => h('button', {
    type: 'button', class: 'cas-chip pick c' + (i % 6) + (L.chip === c ? ' cur' : ''), 'aria-pressed': L.chip === c ? 'true' : 'false',
    'aria-label': tr('chip') + ' ' + fmt(c), 'data-k': 'chip' + c, onclick: () => { L.chip = c; redraw(); },
  }, abbrevChip(c))));
  const kindRow = h('div', { class: 'cas-kinds', role: 'group', 'aria-label': tr('betType') }, KINDS.map((k) => h('button', {
    type: 'button', class: 'cas-kind' + (kind === k ? ' on' : ''), 'aria-pressed': kind === k ? 'true' : 'false', 'data-k': 'kind' + k,
    onclick: () => { L.rlKind = k; L.anchor = null; redraw(); },
  }, tr(k === 'split' ? 'split' : k), h('small', null, (st.pays[k] || 0) + ':1'))));
  const hintKey = { straight: 'hintStraight', split: 'hintSplit', street: 'hintStreet', corner: 'hintCorner', line: 'hintLine' }[kind];

  const betsList = st.bets.length ? h('ul', { class: 'cas-betlist' }, [...agg.values()].map((a) => h('li', { class: reveal ? (a.win ? 'won' : 'lost') : '' },
    h('span', null, betLabel(a)), h('small', null, (st.pays[a.bet]) + ':1'), h('b', null, fmt(a.amount)),
    reveal ? h('em', null, a.win ? '+' + fmt(a.win) : '—') : null))) : h('p', { class: 'cas-muted' }, tr('noBets'));

  const lastBets = over ? st.bets.map((b) => ({ bet: b.bet, target: b.target, amount: b.amount })) : L.rlLast;
  const repeatTotal = (lastBets || []).reduce((s, b) => s + b.amount, 0);
  const repeat = reveal && tb.you != null && lastBets && lastBets.length && repeatTotal <= st.maxTotal ? h('button', {
    type: 'button', class: 'btn ghost', 'data-k': 'repeat', disabled: spinning,
    onclick: async (e) => {
      const b = e.currentTarget; b.disabled = true;
      for (const x of lastBets) {
        const a = { type: 'bet', bet: x.bet, amount: x.amount };
        if (x.target != null) a.target = x.target;
        await ctx.act(a);
      }
    },
  }, '🔁 ' + tr('repeat') + ' · ' + coins(repeatTotal)) : null;

  const spinBtn = !over && st.bets.length && tb.you != null ? h('button', {
    type: 'button', class: 'cas-spin wide', 'data-k': 'spin',
    onclick: async (e) => { L.rlWant = true; await ctx.act({ type: 'spin' }, e.currentTarget); L.rlWant = false; },
  }, h('span', null, tr('spinWheel')), h('small', null, coins(st.total))) : null;

  const net = st.win - st.total;
  return [
    h('div', { class: 'felt cas-rl-felt' },
      h('div', { class: 'cas-rl-top' }, wheel,
        h('div', { class: 'cas-rl-side' },
          h('p', { class: 'cas-rl-call' }, spinning ? tr('spinning') : over ? (reveal ? null : tr('place')) : tr('place')),
          reveal ? outcome(net, st.win, null) : null,
          h('div', { class: 'cas-rl-total' }, h('span', null, tr('totalBet')), h('b', null, coins(st.total)),
            h('small', null, tr('limit', { n: fmt(st.maxTotal) }))),
          chipRow, spinBtn, repeat,
          over && reveal ? h('p', { class: 'cas-muted' }, tr('newRound')) : null)),
      h('div', { class: 'cas-rl-cloth-wrap' },
        kindRow,
        h('p', { class: 'cas-hint' }, anchor != null ? tr('pickPartner') : tr(hintKey)),
        h('div', { class: 'cas-cloth-scroll' }, cloth))),
    h('section', { class: 'cas-rl-bets' }, h('h3', null, tr('yourBets')), betsList, h('p', { class: 'cas-muted' }, tr('final'))),
  ];
}

function isWinOutside(k, target, n) {
  if (n == null || n === 0) return false;
  switch (k) {
    case 'red': return RED.has(n);
    case 'black': return !RED.has(n);
    case 'even': return n % 2 === 0;
    case 'odd': return n % 2 === 1;
    case 'low': return n <= 18;
    case 'high': return n >= 19;
    case 'dozen': return Math.ceil(n / 12) === target;
    case 'column': return ((n - 1) % 3) + 1 === target;
    default: return false;
  }
}

function abbrevChip(n) {
  if (n >= 1000000) return Math.round(n / 100000) / 10 + 'M';
  if (n >= 1000) return (Math.round(n / 100) / 10 + 'k').replace('.0k', 'k');
  return String(n);
}

function wheelSvg(order) {
  const seg = 360 / 37;
  const pt = (r, a) => { const t = (a * Math.PI) / 180; return [r * Math.sin(t), -r * Math.cos(t)]; };
  const pockets = order.map((n, i) => {
    const a0 = i * seg - seg / 2, a1 = i * seg + seg / 2;
    const [x0, y0] = pt(140, a0), [x1, y1] = pt(140, a1), [x2, y2] = pt(86, a1), [x3, y3] = pt(86, a0);
    const fillC = n === 0 ? '#2f8f36' : RED.has(n) ? '#d5321f' : '#1d1a14';
    const [tx, ty] = pt(124, i * seg);
    return [
      svg('path', { d: `M${x0},${y0} A140,140 0 0 1 ${x1},${y1} L${x2},${y2} A86,86 0 0 0 ${x3},${y3} Z`, fill: fillC, stroke: '#e9c46a', 'stroke-width': '1' }),
      svg('text', { x: tx, y: ty, transform: `rotate(${i * seg} ${tx} ${ty})`, 'text-anchor': 'middle', 'dominant-baseline': 'central', class: 'cas-wn' }, String(n)),
    ];
  });
  return svg('svg', { viewBox: '-150 -150 300 300', 'aria-hidden': 'true' },
    svg('circle', { r: 149, fill: '#6d4826', stroke: '#241f14', 'stroke-width': 3 }),
    svg('circle', { r: 141, fill: '#4f3319' }),
    pockets,
    svg('circle', { r: 108, fill: 'none', stroke: '#e9c46a', 'stroke-width': 1 }),
    svg('circle', { r: 86, fill: '#8a5e34', stroke: '#241f14', 'stroke-width': 2 }),
    svg('circle', { r: 62, fill: '#a97b4d', stroke: '#6d4826', 'stroke-width': 3 }),
    [0, 90, 180, 270].map((a) => { const [x, y] = pt(54, a); return svg('line', { x1: 0, y1: 0, x2: x, y2: y, stroke: '#e9b420', 'stroke-width': 7, 'stroke-linecap': 'round' }); }),
    svg('circle', { r: 14, fill: '#e9b420', stroke: '#7f5b06', 'stroke-width': 3 }));
}

// ======================================================================================
// blackjack
// ======================================================================================
const bjTotal = (total, soft, cards) => (cards.length === 2 && total === 21 ? '21' : soft && total < 21 ? `${total - 10}/${total}` : String(total));

/** Cards with a pop-in for the ones not seen yet (keys kept in ctx.local). */
function cardsRow(ctx, prefix, cards, deck, size) {
  const seen = ctx.local.seen || (ctx.local.seen = new Set());
  let k = 0;
  const out = cards.map((c, i) => {
    const key = prefix + ':' + i + ':' + c;
    const fresh = !seen.has(key) && !reduced();
    seen.add(key);
    const el = card(c, { deck, size, cls: fresh ? 'cas-deal' : '' });
    if (fresh) { el.style.animationDelay = (k * 140) + 'ms'; k++; }
    return el;
  });
  if (seen.size > 400) ctx.local.seen = new Set([...seen].slice(-100));
  return h('div', { class: 'cas-cards' }, out);
}

function blackjackView(el, tb, ctx) {
  const st = tb.state;
  const L = ctx.local;
  const over = tb.status === 'over' || st.phase === 'done';
  const max = st.maxBet;
  const legal = new Set((tb.legal || []).map((a) => a.type));
  const r = 'r' + tb.round;
  const totalBet = st.hands.reduce((s, x) => s + x.bet, 0);
  const d = st.dealer;
  const act = (type) => (e) => ctx.act({ type }, e.currentTarget);
  const myTurn = st.phase === 'play' && tb.you != null && legal.size > 0;
  const active = st.hands[st.active];

  const dealer = h('div', { class: 'cas-bj-dealer' },
    h('div', { class: 'cas-who' }, h('span', null, tr('dealer')), d.cards.length ? h('b', { class: 'cas-total' + (d.revealed && d.total > 21 ? ' bust' : '') }, bjTotal(d.total, d.soft, d.revealed ? d.cards : [])) : null),
    d.cards.length ? cardsRow(ctx, r + 'd', d.cards, 'fr', 'md') : h('div', { class: 'cas-cards empty' }, card('??', { deck: 'fr', size: 'md', cls: 'ghost' }), card('??', { deck: 'fr', size: 'md', cls: 'ghost' })));

  const arc = h('p', { class: 'cas-arc' }, tr('bjRule'));

  const hands = st.hands.length ? h('div', { class: 'cas-bj-hands' }, st.hands.map((x, i) => h('div', {
    class: 'cas-hand' + (st.active === i && st.hands.length > 1 ? ' active' : '') + (x.result ? ' res-' + x.result : ''),
  },
  st.hands.length > 1 ? h('small', { class: 'cas-hand-n' }, tr('hand', { n: i + 1 })) : null,
  cardsRow(ctx, r + 'h' + i, x.cards, 'fr', 'lg'),
  h('div', { class: 'cas-hand-info' },
    h('b', { class: 'cas-total' + (x.total > 21 ? ' bust' : '') }, bjTotal(x.total, x.soft, x.cards)),
    h('span', { class: 'cas-chip stake' }, abbrevChip(x.bet)), x.doubled ? h('small', { class: 'cas-tag' }, '×2 ' + tr('doubled')) : null,
    x.result ? h('span', { class: 'cas-badge ' + x.result }, tr('r_' + x.result)) : null)))) : h('p', { class: 'cas-pick' }, tr('bjPick'));

  const controls = myTurn ? h('div', { class: 'cas-actions' },
    h('button', { type: 'button', class: 'btn primary', 'data-k': 'hit', disabled: !legal.has('hit'), onclick: act('hit') }, '🃏 ' + tr('hit')),
    h('button', { type: 'button', class: 'btn danger', 'data-k': 'stand', disabled: !legal.has('stand'), onclick: act('stand') }, '✋ ' + tr('stand')),
    h('button', { type: 'button', class: 'btn coin', 'data-k': 'double', disabled: !legal.has('double'), onclick: act('double') }, '×2 ' + tr('double'),
      legal.has('double') && active ? h('small', null, tr('cost', { n: fmt(active.bet) })) : null),
    h('button', { type: 'button', class: 'btn', 'data-k': 'splitH', disabled: !legal.has('split'), onclick: act('split') }, '✂ ' + tr('splitH'),
      legal.has('split') && active ? h('small', null, tr('cost', { n: fmt(active.bet) })) : null))
    : (st.phase === 'bet' || over) && tb.you != null ? h('div', { class: 'cas-dealbar' }, betPicker(el, tb, ctx, max, false),
      h('button', { type: 'button', class: 'cas-spin', 'data-k': 'deal', onclick: (e) => ctx.act({ type: 'bet', amount: getBet(tb, ctx, max) }, e.currentTarget) },
        h('span', null, over ? tr('dealAgain') : tr('deal')), h('small', null, coins(getBet(tb, ctx, max))))) : null;

  return [
    h('div', { class: 'felt cas-bj-felt' },
      h('div', { class: 'cas-shoe', 'aria-hidden': 'true' }, card('??', { deck: 'fr', size: 'sm' }), h('small', null, tr('shoe', { n: st.shoe }))),
      dealer, arc,
      over && st.hands.length ? outcome(st.win - totalBet, st.win, null) : myTurn ? h('p', { class: 'turn-banner mine' }, tr('yourMove')) : null,
      hands, controls),
  ];
}

// ======================================================================================
// sette e mezzo
// ======================================================================================
function half(v) {
  if (v == null) return '';
  const whole = Math.floor(v);
  const hasHalf = v - whole >= 0.25;
  return whole === 0 && hasHalf ? '½' : String(whole) + (hasHalf ? '½' : '');
}

function semView(el, tb, ctx) {
  const st = tb.state;
  const over = tb.status === 'over' || st.phase === 'done';
  const legal = new Set((tb.legal || []).map((a) => a.type));
  const max = (tb.legal.find((a) => a.type === 'bet') || {}).max || 5000;
  const r = 'r' + tb.round;
  const myTurn = st.phase === 'play' && tb.you != null && legal.size > 0;
  const bankCards = st.bank.cards;

  const bank = h('div', { class: 'cas-sem-bank' },
    h('div', { class: 'cas-who' }, icon('slot_marione', 40), h('span', null, tr('bank')),
      bankCards.length ? h('b', { class: 'cas-total' + (st.bank.total > 7.5 ? ' bust' : '') }, bankCards.every((c) => c === '??') ? '?' : half(st.bank.total) + (bankCards.includes('??') ? '+?' : '')) : null),
    bankCards.length ? cardsRow(ctx, r + 'b', bankCards, 'it', 'md') : h('div', { class: 'cas-cards empty' }, card('??', { deck: 'it', size: 'md', cls: 'ghost' })));

  const mine = st.cards.length ? h('div', { class: 'cas-sem-me' },
    h('div', { class: 'cas-cards-wrap' }, cardsRow(ctx, r + 'p', st.cards, 'it', 'lg'),
      st.phase === 'play' ? h('small', { class: 'cas-covered' }, '👁 ' + tr('covered')) : null),
    h('div', { class: 'cas-hand-info' },
      h('b', { class: 'cas-total big' + (st.total > 7.5 ? ' bust' : st.total === 7.5 ? ' best' : '') }, half(st.total)),
      h('span', { class: 'cas-chip stake' }, abbrevChip(st.bet)),
      null))
    : h('p', { class: 'cas-pick' }, tr('semPick'));

  const controls = myTurn ? h('div', { class: 'cas-actions' },
    h('button', { type: 'button', class: 'btn primary', 'data-k': 'card', disabled: !legal.has('card'), onclick: (e) => ctx.act({ type: 'card' }, e.currentTarget) }, '🃏 ' + tr('card')),
    h('button', { type: 'button', class: 'btn danger', 'data-k': 'stand', disabled: !legal.has('stand'), onclick: (e) => ctx.act({ type: 'stand' }, e.currentTarget) }, '✋ ' + tr('stay')))
    : (st.phase === 'bet' || over) && tb.you != null ? h('div', { class: 'cas-dealbar' }, betPicker(el, tb, ctx, max, false),
      h('button', { type: 'button', class: 'cas-spin', 'data-k': 'deal', onclick: (e) => ctx.act({ type: 'bet', amount: getBet(tb, ctx, max) }, e.currentTarget) },
        h('span', null, over ? tr('playAgain') : tr('play')), h('small', null, coins(getBet(tb, ctx, max))))) : null;

  const gross = st.payout || 0;
  return [
    h('div', { class: 'felt cas-sem-felt' },
      bank,
      h('p', { class: 'cas-arc' }, tr('semRule')),
      over && st.cards.length ? outcome(gross - st.bet, gross, tr('s_' + st.result)) : myTurn ? h('p', { class: 'turn-banner mine' }, tr('yourMove')) : null,
      mine, controls),
  ];
}
