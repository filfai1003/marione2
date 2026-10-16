-- Robbery, soundboard, wealth roles and the persisted chat log (what the AI remembers).
-- Everything lives in this database: nothing is stored in Discord channels.

-- Robbery --------------------------------------------------------------------------------------

alter table marione.ledger drop constraint ledger_reason_check;
alter table marione.ledger add constraint ledger_reason_check check (reason in (
  'chat_reward', 'voice_reward',
  'transfer_out', 'transfer_in',
  'afk_fine', 'afk_drain', 'spam_fine',
  'agent_fine_out', 'agent_fine_in', 'agent_gift_out', 'agent_gift_in',
  'rob_out', 'rob_in', 'rob_fine_out', 'rob_fine_in',
  'admin_adjust', 'reversal'
));

create table marione.heists (
  id          bigint generated always as identity primary key,
  attacker_id bigint not null references marione.members (user_id),
  victim_id   bigint not null references marione.members (user_id),
  amount      bigint not null check (amount > 0),
  success     boolean not null,
  moved       bigint not null default 0,  -- coins actually stolen (success) or paid as a fine
  group_id    uuid,
  created_at  timestamptz not null default now(),
  check (attacker_id <> victim_id)
);
create index heists_attacker_idx on marione.heists (attacker_id, id desc);
create index heists_victim_idx on marione.heists (victim_id, id desc);

-- Resolves one heist atomically. The dice are rolled by the caller (it needs the odds); this
-- function enforces the per-attacker cooldown (from this table, so a restart does not reset it),
-- moves the coins and records the attempt. An attempt the victim cannot cover is refused and does
-- not spend the cooldown.
--   success: the victim pays `amount` to the attacker (all of it or nothing)
--   failure: the attacker pays up to `fine` to the VICTIM
-- Returns (status, moved, wait_seconds); status is 'ok', 'caught', 'cooldown' or 'victim_poor'.
create function marione.resolve_heist(
  p_attacker bigint, p_victim bigint, p_amount bigint, p_success boolean, p_fine bigint,
  p_cooldown_seconds integer, p_key text
) returns table (status text, moved bigint, wait_seconds integer)
language plpgsql as $$
declare
  v_last timestamptz;
  v_wait integer;
  v_group uuid := gen_random_uuid();
  v_moved bigint := 0;
  v_meta jsonb := jsonb_build_object('kind', 'heist', 'amount', p_amount, 'success', p_success);
begin
  if p_attacker = p_victim or p_amount <= 0 then
    raise exception 'invalid heist';
  end if;
  insert into marione.members (user_id) values (p_attacker), (p_victim) on conflict do nothing;
  perform pg_advisory_xact_lock(p_attacker);
  select max(created_at) into v_last from marione.heists where attacker_id = p_attacker;
  if v_last is not null then
    v_wait := ceil(p_cooldown_seconds - extract(epoch from (now() - v_last)))::integer;
    if v_wait > 0 then
      return query select 'cooldown'::text, 0::bigint, v_wait;
      return;
    end if;
  end if;
  if p_success then
    v_moved := marione.move(
      p_victim, p_attacker, p_amount, 'rob_out', 'rob_in', p_key, v_meta, false, v_group);
    if v_moved = 0 then
      return query select 'victim_poor'::text, 0::bigint, 0;
      return;
    end if;
  elsif p_fine > 0 then
    v_moved := marione.move(
      p_attacker, p_victim, p_fine, 'rob_fine_out', 'rob_fine_in', p_key, v_meta, true, v_group);
  end if;
  insert into marione.heists (attacker_id, victim_id, amount, success, moved, group_id)
  values (p_attacker, p_victim, p_amount, p_success, v_moved, v_group);
  return query select case when p_success then 'ok' else 'caught' end, v_moved, 0;
end;
$$;

-- Soundboard (one library for the whole server) -------------------------------------------------

create table marione.soundboard_sounds (
  id           bigint generated always as identity primary key,
  name         text not null check (length(name) between 1 and 40),
  emoji        text not null default '🔊' check (length(emoji) between 1 and 16),
  creator_id   bigint not null references marione.members (user_id),
  content_type text not null,
  data         bytea not null check (octet_length(data) between 1 and 8388608),
  duration_ms  integer not null check (duration_ms between 1 and 30000),
  created_at   timestamptz not null default now()
);
create unique index soundboard_name_uq on marione.soundboard_sounds (lower(name));

create table marione.soundboard_favorites (
  user_id  bigint not null references marione.members (user_id),
  sound_id bigint not null references marione.soundboard_sounds (id) on delete cascade,
  primary key (user_id, sound_id)
);

alter table marione.entrance_sounds add column duration_ms integer;

-- Wealth roles: the Discord roles Marione created, so it only ever touches its own -----------------

create table marione.wealth_roles (
  tier_key text primary key,
  role_id  bigint not null
);

-- Chat log: the live window of every channel survives a restart --------------------------------

create table marione.channel_log (
  id                  bigint generated always as identity primary key,
  channel_id          bigint not null,
  message_id          bigint not null,
  author_id           bigint not null,
  author_name         text not null,
  content             text not null,
  is_bot              boolean not null default false,
  reply_to_message_id bigint,
  created_at          timestamptz not null default now(),
  unique (channel_id, message_id)
);
create index channel_log_channel_idx on marione.channel_log (channel_id, id desc);
create index channel_log_author_idx on marione.channel_log (author_id);
