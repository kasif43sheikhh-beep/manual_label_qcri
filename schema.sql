-- Run this once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run.

-- 1) The pairs the judges will label (this replaces pairs.csv).
create table pairs (
  pair_id    text primary key,           -- your Pair_ID, e.g. "S-0001"
  sentence_1 text not null,
  sentence_2 text not null,
  position   integer not null unique     -- display order; databases do not remember file order
);

-- 2) One row per judgment (this replaces results.xlsx).
create table annotations (
  id                 bigint generated always as identity primary key,
  created_at         timestamptz not null default now(),   -- the database stamps the time
  user_id            text not null check (user_id in ('User 1', 'User 2', 'User 3')),
  pair_id            text not null references pairs (pair_id),
  same_meaning       boolean  not null,
  diversity_score    smallint not null check (diversity_score between 1 and 5),
  time_spent_seconds numeric  not null check (time_spent_seconds >= 0),
  unique (user_id, pair_id)              -- a judge can answer a pair only once
);

-- 3) Lock both tables. With RLS on and no policies, the publishable key sees nothing.
--    Your app uses the secret key, which bypasses RLS, so it still works.
alter table pairs       enable row level security;
alter table annotations enable row level security;

-- Cumulative time is no longer stored per row. It is derived on demand:
--   select user_id, count(*) as done, sum(time_spent_seconds) as seconds
--   from annotations group by user_id;
