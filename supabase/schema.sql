-- co-14ers — schema + RLS
-- Paste this whole file into the Supabase SQL editor and run it.
-- Idempotent: safe to run more than once. Won't drop data.

-- =====================================================================
-- tables
-- =====================================================================

create table if not exists public.summits (
  user_id     uuid not null references auth.users on delete cascade,
  peak_id     text not null,
  summit_date date,
  notes       text,
  created_at  timestamptz not null default now(),
  primary key (user_id, peak_id)
);

create table if not exists public.routes_climbed (
  user_id      uuid not null references auth.users on delete cascade,
  route_key    text not null,
  peak_id      text not null,
  climbed_date date,
  notes        text,
  created_at   timestamptz not null default now(),
  primary key (user_id, route_key)
);

create table if not exists public.planned (
  user_id     uuid not null references auth.users on delete cascade,
  peak_id     text not null,
  target_date date,
  notes       text,
  created_at  timestamptz not null default now(),
  primary key (user_id, peak_id)
);

-- supporting indexes for common queries
create index if not exists summits_user_idx        on public.summits        (user_id);
create index if not exists routes_climbed_user_idx on public.routes_climbed (user_id);
create index if not exists routes_climbed_peak_idx on public.routes_climbed (user_id, peak_id);
create index if not exists planned_user_idx        on public.planned        (user_id);

-- =====================================================================
-- row level security
-- "fully private" — a user can only ever read or write their own rows.
-- =====================================================================

alter table public.summits        enable row level security;
alter table public.routes_climbed enable row level security;
alter table public.planned        enable row level security;

-- summits
drop policy if exists "summits own select" on public.summits;
drop policy if exists "summits own write"  on public.summits;
create policy "summits own select" on public.summits
  for select using (auth.uid() = user_id);
create policy "summits own write" on public.summits
  for all
  using      (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- routes_climbed
drop policy if exists "routes_climbed own select" on public.routes_climbed;
drop policy if exists "routes_climbed own write"  on public.routes_climbed;
create policy "routes_climbed own select" on public.routes_climbed
  for select using (auth.uid() = user_id);
create policy "routes_climbed own write" on public.routes_climbed
  for all
  using      (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- planned
drop policy if exists "planned own select" on public.planned;
drop policy if exists "planned own write"  on public.planned;
create policy "planned own select" on public.planned
  for select using (auth.uid() = user_id);
create policy "planned own write" on public.planned
  for all
  using      (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- =====================================================================
-- post-flight check
-- run these after the migration. each should return zero rows when
-- executed in the SQL editor as the anon role (use "RLS" preview in
-- Table Editor or run via the REST endpoint with the anon key).
-- =====================================================================
-- select * from public.summits;
-- select * from public.routes_climbed;
-- select * from public.planned;
