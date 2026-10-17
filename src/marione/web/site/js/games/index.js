// Renderer per game key: render(el, table, ctx) is called on every update.
import * as trick from './trick.js';
import * as scopa from './scopa.js';
import * as casino from './casino.js';
import * as poker from './poker.js';
import * as chess from './chess.js';
import * as rummy from './rummy.js';

export const RENDERERS = {
  briscola: trick, tresette: trick, bestia: trick,
  scopa,
  slot: casino, roulette: casino, blackjack: casino, settemezzo: casino,
  poker5: poker, texas: poker,
  chess,
  scala40: rummy, machiavelli: rummy,
};
