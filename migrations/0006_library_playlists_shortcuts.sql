-- Music library (mp3 files uploaded to the server, always available), playlists, and the keyboard
-- shortcuts members attach to soundboard sounds.

-- The shared library: every member can play every upload, only the uploader (or an admin) deletes.
create table marione.music_uploads (
  id           bigint generated always as identity primary key,
  title        text not null check (length(title) between 1 and 200),
  uploader_id  bigint not null references marione.members (user_id),
  content_type text not null,
  data         bytea not null,
  duration_ms  integer not null check (duration_ms > 0),
  created_at   timestamptz not null default now()
);
create index music_uploads_title_idx on marione.music_uploads (lower(title));

-- Playlists belong to a member; everyone can see and play them, only the owner (or an admin) edits.
create table marione.playlists (
  id         bigint generated always as identity primary key,
  owner_id   bigint not null references marione.members (user_id),
  name       text not null check (length(name) between 1 and 60),
  created_at timestamptz not null default now()
);
create unique index playlists_owner_name_uq on marione.playlists (owner_id, lower(name));

-- A song in a playlist: the link it is played from, or an upload (deleted with it).
create table marione.playlist_tracks (
  id          bigint generated always as identity primary key,
  playlist_id bigint not null references marione.playlists (id) on delete cascade,
  title       text not null,
  url         text not null,
  duration    integer,
  channel     text,
  thumbnail   text,
  source      text not null default 'youtube',
  upload_id   bigint references marione.music_uploads (id) on delete cascade,
  added_at    timestamptz not null default now()
);
create index playlist_tracks_playlist_idx on marione.playlist_tracks (playlist_id, id);

-- One key combination per sound per member (and a combination opens only one sound).
create table marione.soundboard_shortcuts (
  user_id  bigint not null references marione.members (user_id),
  sound_id bigint not null references marione.soundboard_sounds (id) on delete cascade,
  key      text not null check (length(key) between 1 and 24),
  primary key (user_id, sound_id),
  unique (user_id, key)
);
