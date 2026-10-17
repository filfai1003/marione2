// Games: the lobby (#/games) and a table (#/games/<id>). Each game draws itself through a
// renderer in js/games/ that receives the table and a small context (act, names, local state).
import { h, fill, fmt } from '../util.js';
import { store } from '../store.js';
import { api, post } from '../api.js';
import { run, handleError, refreshState } from '../data.js';
import { t } from '../i18n.js';
import { pageHead, notice, btn, empty, modal, chipGroup, field } from '../ui.js';
import { icon } from '../art.js';
import { RENDERERS } from '../games/index.js';

// Lobby sections, in order.
export const SECTIONS = [
  ['casino', ['slot', 'roulette', 'blackjack', 'settemezzo']],
  ['poker', ['texas', 'poker5']],
  ['italian', ['briscola', 'scopa', 'tresette', 'bestia']],
  ['rummy', ['scala40', 'machiavelli']],
  ['strategy', ['chess']],
];
const gname = (k) => t('gname.' + k);
const modeName = (m) => t('gmode.' + m.replace(/^(\d)p$/, 'np'), { n: m[0] });

export function mount(root, sub) {
  let view = null, current = undefined;
  function open(s) {
    if (s === current && view) return; // the app calls route() on every refresh: same table, keep it
    current = s;
    if (view && view.destroy) view.destroy();
    root.replaceChildren();
    view = s ? tableView(root, s) : lobbyView(root);
    if (store.state) view.update();
  }
  open(sub);
  return {
    update: () => view && view.update(),
    route: (s) => open(s),
    tick: () => view && view.tick && view.tick(),
    destroy: () => view && view.destroy && view.destroy(),
  };
}

// ======================================================================================
// lobby
// ======================================================================================
function lobbyView(root) {
  const off = h('div');
  const mine = h('div');
  const open = h('div');
  const sections = h('div', { class: 'stack-lg' });
  const side = h('div', { class: 'stack' });
  root.append(pageHead(t('games.title'), t('games.sub')), off,
    h('div', { class: 'games-layout' }, h('div', { class: 'stack-lg' }, mine, sections), h('aside', { class: 'stack' }, open, side)));
  let data = null, timer = null;

  async function load() {
    try { data = await api('/api/games'); draw(); } catch (e) { handleError(e); }
  }
  function draw() {
    if (!data) return;
    const byKey = Object.fromEntries(data.games.map((g) => [g.key, g]));
    const myTables = data.tables.filter((tb) => tb.humans.includes(data.you));
    const others = data.tables.filter((tb) => !tb.humans.includes(data.you) && tb.status === 'waiting');
    fill(mine, myTables.length ? h('section', { class: 'card' },
      h('div', { class: 'card-title' }, icon('games', 30), h('h2', null, t('games.yourTables'))),
      h('ul', { class: 'tbl-list' }, myTables.map((tb) => tableRow(tb, h('a', { class: 'btn primary sm', href: '#/games/' + tb.id }, t('games.resume')))))) : null);
    fill(sections, SECTIONS.map(([sec, keys]) => h('section', { class: 'stack' },
      h('h2', { class: 'section-title' }, t('games.sec.' + sec)),
      h('div', { class: 'game-grid' }, keys.filter((k) => byKey[k]).map((k) => gameTile(byKey[k]))))));
    fill(open, h('section', { class: 'card' },
      h('div', { class: 'card-title' }, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, '🪑'), h('h2', null, t('games.openTables'))),
      others.length ? h('ul', { class: 'tbl-list' }, others.map((tb) => tableRow(tb,
        btn(t('games.join'), 'primary sm', { onclick: (e) => run(e.currentTarget, async () => {
          await post('/api/games/join', { tableId: tb.id });
          location.hash = '#/games/' + tb.id;
        }) })))) : empty('🍽️', t('games.noOpen'))));
    fill(side, data.top.length ? h('section', { class: 'card' },
      h('div', { class: 'card-title' }, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, '🏆'), h('h2', null, t('games.topWeek'))),
      h('ol', { class: 'top-list' }, data.top.map((p) => h('li', null, h('span', null, p.name), h('strong', null, '+' + fmt(p.net) + ' 🪙'))))) : null,
    data.stats.length ? h('section', { class: 'card' },
      h('div', { class: 'card-title' }, h('span', { class: 'ct-emoji', 'aria-hidden': 'true' }, '📊'), h('h2', null, t('games.yourStats'))),
      h('ul', { class: 'stat-list' }, data.stats.map((s) => h('li', null, icon(s.game, 24), h('span', null, gname(s.game)),
        h('small', null, t('games.wonOf', { won: s.won, played: s.played })),
        h('strong', { class: s.net >= 0 ? 'pos' : 'neg' }, (s.net >= 0 ? '+' : '−') + fmt(Math.abs(s.net))))))) : null);
  }
  function tableRow(tb, action) {
    const seated = tb.seats.filter(Boolean).length;
    return h('li', { class: 'tbl-row' }, icon(tb.game, 40),
      h('span', { class: 'tbl-main' }, h('strong', null, gname(tb.game) + ' · ' + modeName(tb.mode)),
        h('small', null, [tb.seats.filter(Boolean).map((s) => s.name).join(', '), `${seated}/${tb.seats.length}`,
          tb.stake ? fmt(tb.stake) + ' 🪙' : null].filter(Boolean).join(' · '))), action);
  }
  function gameTile(g) {
    const seats = g.modes.map((m) => m.seats);
    const players = Math.min(...seats) === Math.max(...seats)
      ? (seats[0] === 1 ? t('games.solo') : t('games.players', { n: seats[0] }))
      : t('games.playersRange', { a: Math.min(...seats), b: Math.max(...seats) });
    return h('button', { type: 'button', class: 'game-tile', onclick: () => createDialog(g) },
      icon(g.key, 72), h('strong', null, gname(g.key)), h('small', null, t('gdesc.' + g.key)),
      h('span', { class: 'tag counter' }, g.house ? t('games.vsBank') : players));
  }

  function update() {
    const on = store.state.modules.games && store.state.modules.economy;
    fill(off, on ? null : notice('🎲', t('games.offTitle'), t('games.offText')));
    mine.hidden = sections.hidden = open.hidden = side.hidden = !on;
    if (on && !timer) { load(); timer = setInterval(() => { if (!document.hidden) load(); }, 8000); }
  }
  return { update, destroy() { clearInterval(timer); } };
}

// ---------- "new table" dialog ----------
function createDialog(g) {
  let mode = g.modes[0].key;
  const modeChips = g.modes.length > 1
    ? chipGroup(g.modes.map((m) => [m.key, modeName(m.key)]), mode, (k) => { mode = k; }, t('games.mode')) : null;
  const stake = h('input', { type: 'number', min: '0', step: '1', inputmode: 'numeric', value: g.house ? '10' : '50' });
  const quick = h('div', { class: 'chips' }, [10, 50, 100, 500, 1000].map((v) =>
    h('button', { type: 'button', class: 'chip-btn', onclick: () => { stake.value = v; } }, fmt(v))));
  const opts = {};
  const extra = [];
  if (g.key === 'chess') {
    const names = [t('games.level1'), t('games.level2'), t('games.level3'), t('games.level4'), t('games.level5')];
    const level = h('select', null, names.map((name, i) => h('option', { value: i + 1, selected: i === 2 }, name)));
    level.addEventListener('change', () => { opts.level = Number(level.value); });
    opts.level = 3;
    extra.push(field(t('games.botLevel'), level));
  }
  if (g.key === 'scopa' || g.key === 'tresette') {
    const targets = g.key === 'scopa' ? [11, 21] : [11, 21, 31];
    const target = h('select', null, h('option', { value: '1' }, t('games.oneHand')),
      targets.map((n) => h('option', { value: n, selected: n === targets[0] }, t('games.toPoints', { n }))));
    const set = () => { if (target.value === '1') { opts.hands = 1; delete opts.target; } else { opts.target = Number(target.value); delete opts.hands; } };
    target.addEventListener('change', set); set();
    extra.push(field(t('games.length'), target));
  }
  const balance = h('p', { class: 'hint' }, t('games.youHave', { amount: fmt(store.balance) }));
  const stakeLabel = g.house ? t('games.baseBet') : g.economy === 'bets' ? t('games.unit') : t('games.stake');
  const stakeHint = g.house ? t('games.baseBetHint') : g.economy === 'bets' ? t('games.unitHint') : t('games.stakeHint');
  const body = h('div', { class: 'stack' },
    h('div', { class: 'create-head' }, icon(g.key, 64), h('div', null, h('p', null, t('gdesc.' + g.key)),
      h('a', { class: 'link small', href: '#', onclick: (e) => { e.preventDefault(); rulesDialog(g.key); } }, '📖 ' + t('games.rules')))),
    modeChips ? h('div', { class: 'field' }, h('span', { class: 'field-label' }, t('games.mode')), modeChips) : null,
    field(stakeLabel, stake, stakeHint), quick, ...extra, balance);
  const create = (bots) => async (e) => {
    const b = e.currentTarget;
    await run(b, async () => {
      const r = await post('/api/games/create', { game: g.key, mode, stake: Math.max(0, Math.floor(Number(stake.value) || 0)), bots, options: opts });
      close();
      await refreshState();
      location.hash = '#/games/' + r.table.id;
    });
  };
  const solo = g.modes.every((m) => m.seats === 1);
  const { close } = modal(gname(g.key), body, () => solo
    ? [btn('▶ ' + t('games.play'), 'primary', { onclick: create(true) })]
    : [btn('👥 ' + t('games.openForFriends'), 'ghost', { onclick: create(false) }),
      btn('🤖 ' + t('games.playBots'), 'primary', { onclick: create(true) })]);
}

export function rulesDialog(key) {
  modal(gname(key) + ' · ' + t('games.rules'), h('div', { class: 'rules' },
    t('grules.' + key).split('\n').map((line) => h('p', null, line))));
}

// ======================================================================================
// a table
// ======================================================================================
function tableView(root, id) {
  const head = h('div', { class: 'tbl-head' });
  const seatsEl = h('div', { class: 'seats' });
  const board = h('div', { class: 'board' });
  const result = h('div');
  const logEl = h('ol', { class: 'glog' });
  root.append(head, seatsEl, result, board,
    h('details', { class: 'card fold glog-fold' }, h('summary', null, h('span', { class: 'fold-title' }, h('h2', null, t('games.log')))), h('div', { class: 'fold-body' }, logEl)));
  let table = null, alive = true, version = -1, failures = 0;
  const local = {}; // the renderer's own state (selected cards...), kept across updates

  const ctx = {
    get table() { return table; },
    local,
    t,
    async act(action, b) {
      const go = async () => {
        const r = await post('/api/games/act', { tableId: id, action });
        apply(r.table);
        refreshState();
      };
      if (b) return run(b, go);
      try { return await go(); } catch (e) { handleError(e); return undefined; }
    },
    name: (i) => (table && table.seats[i] ? table.seats[i].name : '—'),
    you: () => (table ? table.you : null),
    rel: (i) => (table && table.you != null ? (i - table.you + table.seats.length) % table.seats.length : i),
  };

  function apply(tb) {
    if (!tb || (table && tb.version < table.version)) return;
    table = tb;
    version = tb.version;
    draw();
  }

  async function poll() {
    while (alive) {
      try {
        const r = await api(`/api/games/table?id=${encodeURIComponent(id)}&v=${version}`);
        failures = 0;
        apply(r.table);
      } catch (e) {
        if (e.code === 'not_found') { gone(); return; }
        failures += 1;
        await new Promise((res) => setTimeout(res, Math.min(10000, 1000 * failures)));
      }
    }
  }

  function gone() {
    alive = false;
    fill(board, notice('🍽️', t('games.goneTitle'), t('games.goneText'), h('a', { class: 'btn primary', href: '#/games' }, t('games.backToLobby'))));
    fill(head); fill(seatsEl); fill(result);
  }

  function draw() {
    const tb = table;
    const me = tb.you;
    const amOwner = store.me && tb.owner === String(store.me.id);
    fill(head, h('a', { class: 'crumb', href: '#/games' }, '‹ ' + t('nav.games')),
      h('div', { class: 'tbl-title' }, icon(tb.game, 44), h('div', null, h('h1', null, gname(tb.game)),
        h('small', null, [modeName(tb.mode), tb.stake ? (GAME_BETS[tb.game] ? t('games.unitIs', { n: fmt(tb.stake) }) : t('games.stakeIs', { n: fmt(tb.stake) })) : null].filter(Boolean).join(' · ')))),
      h('div', { class: 'tbl-tools' },
        h('button', { type: 'button', class: 'icon-btn round', title: t('games.rules'), 'aria-label': t('games.rules'), onclick: () => rulesDialog(tb.game) }, '📖'),
        me != null ? btn(t('games.leave'), 'ghost sm', { onclick: (e) => leave(e.currentTarget) }) : null));
    // seats
    const teamOf = (i) => tb.teams.findIndex((tm) => tm.includes(i));
    fill(seatsEl, tb.seats.length > 1 ? tb.seats.map((s, i) => h('div', {
      class: 'seat' + (tb.toAct.includes(i) ? ' turn' : '') + (i === me ? ' me' : '') + (s && s.bot ? ' bot' : '') + (teamOf(i) >= 0 ? ' team' + teamOf(i) : ''),
    },
    h('span', { class: 'seat-av', 'aria-hidden': 'true' }, s ? (s.bot ? '🤖' : (s.name || '?')[0].toUpperCase()) : '＋'),
    h('span', { class: 'seat-name' }, s ? s.name : t('games.emptySeat'), i === me ? h('small', null, ' · ' + t('common.you')) : null,
      s && s.auto ? h('small', null, ' · ' + t('games.autoplay')) : null),
    tb.status === 'waiting' && amOwner && s && s.bot ? h('button', { type: 'button', class: 'icon-btn', 'aria-label': t('games.removeBot'),
      onclick: () => post('/api/games/kick', { tableId: id, seat: i }).then((r) => apply(r.table)).catch(handleError) }, '✕') : null)) : null);
    // waiting room
    if (tb.status === 'waiting') {
      fill(result);
      const free = tb.seats.filter((s) => !s).length;
      fill(board, h('section', { class: 'card waiting' },
        h('div', { class: 'notice-emoji mar-anim-bob', 'aria-hidden': 'true' }, '🪑'),
        h('h2', null, t('games.waitingTitle')),
        h('p', { class: 'muted' }, free ? t('games.waitingText', { n: free }) : t('games.readyText')),
        h('div', { class: 'row-center' },
          amOwner && free ? btn('🤖 ' + t('games.addBot'), 'ghost', { onclick: (e) => run(e.currentTarget, async () => apply((await post('/api/games/bot', { tableId: id })).table)) }) : null,
          me == null ? btn(t('games.join'), 'primary', { onclick: (e) => run(e.currentTarget, async () => apply((await post('/api/games/join', { tableId: id })).table)) }) : null,
          amOwner ? btn('▶ ' + t('games.start') + (free ? ' ' + t('games.withBots') : ''), 'primary', { onclick: (e) => start(e.currentTarget) }) : h('p', { class: 'hint' }, t('games.ownerStarts')))));
      fill(logEl);
      return;
    }
    // result banner
    const house = GAME_HOUSE[tb.game];
    if (tb.status === 'over' && tb.result && !house) {
      const net = me != null && store.me ? tb.result.nets[String(store.me.id)] : null;
      const won = net != null && net > 0, lost = net != null && net < 0;
      fill(result, h('section', { class: 'result-banner ' + (won ? 'win' : lost ? 'lose' : 'draw') },
        h('span', { class: 'rb-emoji', 'aria-hidden': 'true' }, won ? '🏆' : lost ? '🍝' : '🤝'),
        h('div', null, h('strong', null, won ? t('games.youWon') : lost ? t('games.youLost') : net === 0 ? t('games.draw') : t('games.matchOver')),
          net ? h('p', null, (net > 0 ? '+' : '−') + fmt(Math.abs(net)) + ' 🪙') : null),
        me != null ? btn('🔁 ' + t('games.again'), 'primary', { onclick: (e) => start(e.currentTarget) }) : null));
    } else fill(result);
    const renderer = RENDERERS[tb.game];
    if (renderer && tb.state) renderer.render(board, tb, ctx);
    else fill(board, empty('🎲', t('games.noRenderer')));
    fill(logEl, (tb.log || []).slice().reverse().map((e) => h('li', null, logLine(tb, e))));
  }

  function logLine(tb, e) {
    const who = e.seat != null ? ctx.name(e.seat) : '';
    const bits = Object.entries(e).filter(([k]) => k !== 'kind' && k !== 'seat').map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : typeof v === 'object' && v ? JSON.stringify(v) : v}`);
    return [who ? h('strong', null, who + ' ') : null, t('glog.' + e.kind) !== 'glog.' + e.kind ? t('glog.' + e.kind) : e.kind, bits.length ? h('small', null, ' · ' + bits.join(' · ')) : null];
  }

  async function start(b) {
    await run(b, async () => { apply((await post('/api/games/start', { tableId: id })).table); await refreshState(); });
  }
  async function leave(b) {
    await run(b, async () => {
      await post('/api/games/leave', { tableId: id });
      alive = false;
      await refreshState();
      location.hash = '#/games';
    });
  }

  (async () => {
    try { apply((await api('/api/games/table?id=' + encodeURIComponent(id))).table); poll(); } catch (e) {
      if (e.code === 'not_found') gone(); else handleError(e);
    }
  })();

  return {
    update() {},
    tick() { if (table && table.turnLeft != null) { table.turnLeft = Math.max(0, table.turnLeft - 1); const el = board.querySelector('[data-turnleft]'); if (el) el.textContent = table.turnLeft + 's'; } },
    destroy() { alive = false; if (RENDERERS[table && table.game] && RENDERERS[table.game].destroy) RENDERERS[table.game].destroy(); },
  };
}

const GAME_HOUSE = { slot: true, roulette: true, blackjack: true, settemezzo: true };
const GAME_BETS = { slot: true, roulette: true, blackjack: true, settemezzo: true, poker5: true, texas: true };
