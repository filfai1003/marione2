-- The music player's history, and what Marione observes about members' habits (when they are
-- online, in voice, what they play, when they write). Kept 90 days; `/marione forget` erases it.

create table marione.music_plays (
  id        bigint generated always as identity primary key,
  user_id   bigint not null,
  title     text not null,
  url       text not null,
  duration  integer,
  source    text not null default 'youtube',
  played_at timestamptz not null default now()
);
create index music_plays_user_idx on marione.music_plays (user_id, id desc);
create index music_plays_time_idx on marione.music_plays (played_at desc);

-- Spans: a row opens when something starts and closes when it ends (ended_at null = still going).
create table marione.presence_spans (
  id         bigint generated always as identity primary key,
  user_id    bigint not null,
  status     text not null check (status in ('online', 'idle', 'dnd')),
  started_at timestamptz not null default now(),
  ended_at   timestamptz
);
create index presence_spans_user_idx on marione.presence_spans (user_id, started_at desc);
create unique index presence_spans_open on marione.presence_spans (user_id) where ended_at is null;

create table marione.activity_spans (
  id         bigint generated always as identity primary key,
  user_id    bigint not null,
  kind       text not null check (kind in ('playing', 'streaming', 'listening', 'watching', 'competing')),
  name       text not null check (length(name) between 1 and 200),
  details    text,
  started_at timestamptz not null default now(),
  ended_at   timestamptz
);
create index activity_spans_user_idx on marione.activity_spans (user_id, started_at desc);
create unique index activity_spans_open on marione.activity_spans (user_id, kind, name) where ended_at is null;

create table marione.voice_spans (
  id           bigint generated always as identity primary key,
  user_id      bigint not null,
  channel_id   bigint not null,
  channel_name text not null,
  started_at   timestamptz not null default now(),
  ended_at     timestamptz
);
create index voice_spans_user_idx on marione.voice_spans (user_id, started_at desc);
create unique index voice_spans_open on marione.voice_spans (user_id) where ended_at is null;

-- Messages per member per local hour (a count, never the text).
create table marione.message_hours (
  user_id  bigint not null,
  day      date not null,
  hour     smallint not null check (hour between 0 and 23),
  messages integer not null default 0,
  primary key (user_id, day, hour)
);
