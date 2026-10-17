-- Games: bets, wins and refunds go through the ledger like everything else; coins in play are
-- recorded as escrow so a restart in the middle of a match gives them back.

alter table marione.ledger drop constraint ledger_reason_check;
alter table marione.ledger add constraint ledger_reason_check check (reason in (
  'chat_reward', 'voice_reward',
  'transfer_out', 'transfer_in',
  'afk_fine', 'afk_drain', 'spam_fine',
  'agent_fine_out', 'agent_fine_in', 'agent_gift_out', 'agent_gift_in',
  'rob_out', 'rob_in', 'rob_fine_out', 'rob_fine_in',
  'admin_adjust', 'reversal', 'legacy_import',
  'game_bet', 'game_win', 'game_refund'
));

create table marione.game_escrow (
  id         bigint generated always as identity primary key,
  table_id   text not null,
  user_id    bigint not null references marione.members (user_id),
  amount     bigint not null check (amount > 0),
  created_at timestamptz not null default now()
);
create index game_escrow_table_idx on marione.game_escrow (table_id);

-- One row per member per finished match or round: what they won or lost.
create table marione.game_results (
  id         bigint generated always as identity primary key,
  game       text not null,
  user_id    bigint not null references marione.members (user_id),
  net        bigint not null,
  created_at timestamptz not null default now()
);
create index game_results_user_idx on marione.game_results (user_id, created_at desc);
create index game_results_game_idx on marione.game_results (game, created_at desc);
