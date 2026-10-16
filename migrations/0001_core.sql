-- Marione core schema. Lives in its own schema so it can share FFT's Postgres server without
-- touching the `public` schema that PostgREST exposes.
--
-- Rules that hold even if the application has a bug (defence in depth, like FFT's DB checks):
--   * a balance can never be negative;
--   * the balance of a member is ALWAYS the sum of their ledger entries (see balance_audit);
--   * an AI action can never move more than 500 coins in one entry;
--   * the same idempotency key can never be applied twice.

create schema if not exists marione;

create table marione.members (
  user_id      bigint primary key,
  display_name text not null default '',
  updated_at   timestamptz not null default now()
);

create table marione.balances (
  user_id    bigint primary key references marione.members (user_id),
  balance    bigint not null default 0 check (balance >= 0),
  updated_at timestamptz not null default now()
);

create table marione.ledger (
  id              bigint generated always as identity primary key,
  group_id        uuid not null default gen_random_uuid(),
  user_id         bigint not null references marione.members (user_id),
  delta           bigint not null check (delta <> 0),
  reason          text not null check (reason in (
    'chat_reward', 'voice_reward',
    'transfer_out', 'transfer_in',
    'afk_fine', 'afk_drain', 'spam_fine',
    'agent_fine_out', 'agent_fine_in', 'agent_gift_out', 'agent_gift_in',
    'admin_adjust', 'reversal'
  )),
  counterparty    bigint references marione.members (user_id),
  idempotency_key text unique,
  meta            jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  constraint agent_entry_cap check (
    reason not in ('agent_fine_out', 'agent_fine_in', 'agent_gift_out', 'agent_gift_in')
    or abs(delta) <= 500
  )
);
create index ledger_user_idx on marione.ledger (user_id, id desc);
create index ledger_group_idx on marione.ledger (group_id);

-- Every member's balance must equal the sum of their ledger: this view must always be empty.
create view marione.balance_audit as
select b.user_id, b.balance, coalesce(sum(l.delta), 0)::bigint as ledger_sum
from marione.balances b
left join marione.ledger l on l.user_id = b.user_id
group by b.user_id, b.balance
having b.balance <> coalesce(sum(l.delta), 0);

-- Applies one signed change to one member, atomically. Returns the change actually applied.
--   p_clamp: a negative change is cut to what the member has (a fine takes the last coins);
--            without it, an overdraft raises (the balance check refuses it).
-- The idempotency key makes a retry a no-op that returns the first result.
create function marione.apply_delta(
  p_user bigint, p_delta bigint, p_reason text,
  p_counterparty bigint default null, p_key text default null,
  p_meta jsonb default '{}'::jsonb, p_clamp boolean default true,
  p_group uuid default gen_random_uuid()
) returns bigint
language plpgsql as $$
declare
  v_balance bigint;
  v_applied bigint;
  v_existing bigint;
begin
  if p_key is not null then
    select delta into v_existing from marione.ledger where idempotency_key = p_key;
    if found then
      return v_existing;
    end if;
  end if;
  insert into marione.members (user_id) values (p_user) on conflict do nothing;
  if p_counterparty is not null then
    insert into marione.members (user_id) values (p_counterparty) on conflict do nothing;
  end if;
  insert into marione.balances (user_id) values (p_user) on conflict do nothing;
  select balance into v_balance from marione.balances where user_id = p_user for update;
  v_applied := case when p_clamp then greatest(p_delta, -v_balance) else p_delta end;
  if v_applied = 0 then
    return 0;
  end if;
  insert into marione.ledger (group_id, user_id, delta, reason, counterparty, idempotency_key, meta)
  values (p_group, p_user, v_applied, p_reason, p_counterparty, p_key, p_meta);
  update marione.balances
     set balance = balance + v_applied, updated_at = now()
   where user_id = p_user;
  return v_applied;
end;
$$;

-- Moves coins from one member to another in ONE transaction (both entries or none).
--   p_partial: move at most what the sender has (fines) instead of refusing (payments, gifts).
-- Returns the amount moved (0 if refused). The two rows are locked in id order: no deadlocks.
create function marione.move(
  p_from bigint, p_to bigint, p_amount bigint,
  p_reason_out text, p_reason_in text,
  p_key text default null, p_meta jsonb default '{}'::jsonb, p_partial boolean default false,
  p_group uuid default gen_random_uuid()
) returns bigint
language plpgsql as $$
declare
  v_group uuid := p_group;
  v_from_balance bigint;
  v_moved bigint;
  v_existing bigint;
begin
  if p_amount <= 0 or p_from = p_to then
    raise exception 'invalid move: % from % to %', p_amount, p_from, p_to;
  end if;
  if p_key is not null then
    select -delta into v_existing from marione.ledger where idempotency_key = p_key || ':out';
    if found then
      return v_existing;
    end if;
  end if;
  insert into marione.members (user_id) values (p_from), (p_to) on conflict do nothing;
  insert into marione.balances (user_id) values (p_from), (p_to) on conflict do nothing;
  perform 1 from marione.balances where user_id in (p_from, p_to) order by user_id for update;
  select balance into v_from_balance from marione.balances where user_id = p_from;
  v_moved := case when p_partial then least(p_amount, v_from_balance) else p_amount end;
  if v_moved <= 0 or v_from_balance < v_moved then
    return 0;
  end if;
  perform marione.apply_delta(
    p_from, -v_moved, p_reason_out, p_to,
    case when p_key is null then null else p_key || ':out' end, p_meta, false, v_group);
  perform marione.apply_delta(
    p_to, v_moved, p_reason_in, p_from,
    case when p_key is null then null else p_key || ':in' end, p_meta, false, v_group);
  return v_moved;
end;
$$;

-- Undoes a whole operation (every entry of its group), as new compensating entries:
-- the ledger is never edited. Safe to call twice (idempotent). Returns the entries reversed.
create function marione.reverse_group(p_group uuid) returns integer
language plpgsql as $$
declare
  r record;
  v_count integer := 0;
  v_done bigint;
begin
  for r in
    select id, user_id, delta, counterparty from marione.ledger
     where group_id = p_group and reason <> 'reversal' order by id
  loop
    continue when exists (
      select 1 from marione.ledger where idempotency_key = 'reversal:' || r.id
    );
    v_done := marione.apply_delta(
      r.user_id, -r.delta, 'reversal', r.counterparty,
      'reversal:' || r.id, jsonb_build_object('reverses', r.id), true);
    if v_done <> 0 then
      v_count := v_count + 1;
    end if;
  end loop;
  return v_count;
end;
$$;

-- Settings -------------------------------------------------------------------------------------

create table marione.settings (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);

-- Entrance sounds (played when a member joins a voice channel) -------------------------------

create table marione.entrance_sounds (
  id           uuid primary key default gen_random_uuid(),
  user_id      bigint not null references marione.members (user_id),
  name         text not null check (length(name) between 1 and 60),
  content_type text not null,
  data         bytea not null check (octet_length(data) between 1 and 8388608),
  created_at   timestamptz not null default now(),
  unique (user_id, name)
);

-- AI: memory and cost ------------------------------------------------------------------------

create table marione.memory_facts (
  id         bigint generated always as identity primary key,
  user_id    bigint not null references marione.members (user_id),
  category   text not null check (category in (
    'identity', 'likes', 'dislikes', 'opinions', 'personality', 'humor', 'relationship', 'notes'
  )),
  text       text not null check (length(text) between 1 and 300),
  confidence smallint not null default 3 check (confidence between 1 and 5),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index memory_facts_unique on marione.memory_facts (user_id, category, lower(text));

create table marione.episodes (
  id           bigint generated always as identity primary key,
  participants bigint[] not null,
  text         text not null check (length(text) between 1 and 400),
  created_at   timestamptz not null default now()
);
create index episodes_participants_idx on marione.episodes using gin (participants);

create table marione.session_summaries (
  channel_id bigint primary key,
  summary    text not null,
  updated_at timestamptz not null default now()
);

create table marione.llm_usage (
  id                bigint generated always as identity primary key,
  role              text not null,
  model             text not null,
  prompt_tokens     integer not null default 0 check (prompt_tokens >= 0),
  completion_tokens integer not null default 0 check (completion_tokens >= 0),
  cost_usd          numeric(12, 6) not null default 0 check (cost_usd >= 0),
  created_at        timestamptz not null default now()
);
create index llm_usage_created_idx on marione.llm_usage (created_at);
