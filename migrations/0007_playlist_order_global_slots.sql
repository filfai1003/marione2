-- Playlists can be reordered, and a sound can take one of the browser extension's global slots.

alter table marione.playlist_tracks add column position integer;
update marione.playlist_tracks t set position = n.rank
  from (select id, row_number() over (partition by playlist_id order by id) as rank
          from marione.playlist_tracks) n
 where n.id = t.id;
alter table marione.playlist_tracks alter column position set not null;
create index playlist_tracks_order_idx on marione.playlist_tracks (playlist_id, position, id);

-- The extension has four global keyboard commands; a member points each at one of their sounds.
create table marione.soundboard_slots (
  user_id  bigint not null references marione.members (user_id),
  slot     smallint not null check (slot between 1 and 4),
  sound_id bigint not null references marione.soundboard_sounds (id) on delete cascade,
  primary key (user_id, slot),
  unique (user_id, sound_id)
);
