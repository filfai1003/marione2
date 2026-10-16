-- Importing the old Marione (data kept as messages in its #marione-data channel).

-- Old balances come in as their own kind of entry, so the history says where they came from.
alter table marione.ledger drop constraint ledger_reason_check;
alter table marione.ledger add constraint ledger_reason_check check (reason in (
  'chat_reward', 'voice_reward',
  'transfer_out', 'transfer_in',
  'afk_fine', 'afk_drain', 'spam_fine',
  'agent_fine_out', 'agent_fine_in', 'agent_gift_out', 'agent_gift_in',
  'rob_out', 'rob_in', 'rob_fine_out', 'rob_fine_in',
  'admin_adjust', 'reversal', 'legacy_import'
));

-- The old soundboard had no length limit: imported sounds may last up to 2 minutes
-- (new uploads are still limited to 30 seconds by the application).
alter table marione.soundboard_sounds drop constraint soundboard_sounds_duration_ms_check;
alter table marione.soundboard_sounds
  add constraint soundboard_sounds_duration_ms_check check (duration_ms between 1 and 120000);

-- Which old storage message became which new row: re-running the import changes nothing.
create table marione.legacy_imports (
  message_id  bigint not null,
  kind        text not null,
  target      text,
  imported_at timestamptz not null default now(),
  primary key (message_id, kind)
);
