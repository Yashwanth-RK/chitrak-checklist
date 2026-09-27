-- =============================================================================
--  Chitrak — Rulebook & TI Checklist
--  Supabase schema
--
--  Design note: the rule TEXT (codes, titles, official wording for all 239
--  items) lives in the HTML file, not in the database. It is immutable
--  reference content that ships with the app. The database stores only the
--  MUTABLE state a team changes: completion, notes and timestamps. That keeps
--  the sync surface to ~239 tiny rows instead of duplicating the rulebook, and
--  it means wording corrections ship with a file update rather than a migration.
-- =============================================================================

-- ── Rulebook checklist state ────────────────────────────────────────────────
create table if not exists public.rule_state (
  rule_id      text primary key,          -- matches RULES_SEED[].id, e.g. 'c-041'
  completed    boolean not null default false,
  note         text    not null default '',
  completed_at timestamptz,
  updated_at   timestamptz not null default now()
);

-- ── Technical Inspection checklist state ────────────────────────────────────
create table if not exists public.inspection_state (
  item_id      text primary key,          -- matches INSPECTION_SEED[].id
  completed    boolean not null default false,
  note         text    not null default '',
  completed_at timestamptz,
  updated_at   timestamptz not null default now()
);

-- ── Team members ────────────────────────────────────────────────────────────
create table if not exists public.team_members (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  role       text not null default '',
  created_at timestamptz not null default now()
);

-- ── Small key/value store (last-saved time, UI prefs, project id) ───────────
create table if not exists public.app_meta (
  key        text primary key,
  value      jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- ── Indexes ─────────────────────────────────────────────────────────────────
create index if not exists rule_state_updated_idx      on public.rule_state (updated_at);
create index if not exists inspection_state_updated_idx on public.inspection_state (updated_at);
create index if not exists team_members_created_idx     on public.team_members (created_at);

-- ── Row population ──────────────────────────────────────────────────────────
-- No seed data is required. The client upserts a row for EVERY item on save, so
-- both tables fill themselves on first use (173 + 66 rows). Untouched items are
-- stamped with the epoch rather than now(), so that a default item left behind by
-- a boot which then failed cannot out-rank real team progress in the
-- last-write-wins merge. Tables may therefore sit empty until somebody ticks
-- something -- that is expected, not a broken setup.

-- ── Row Level Security ──────────────────────────────────────────────────────
-- Enabled so that turning on Supabase Auth later is a one-line change rather
-- than a rewrite. While no auth is configured the anon role is allowed through
-- (see the policies below), which is what makes the MVP usable with just an
-- anon key. See SETUP.md -> "Adding authentication" before exposing this URL.
alter table public.rule_state       enable row level security;
alter table public.inspection_state enable row level security;
alter table public.team_members     enable row level security;
alter table public.app_meta         enable row level security;

drop policy if exists "anon read rule_state"       on public.rule_state;
drop policy if exists "anon write rule_state"       on public.rule_state;
drop policy if exists "anon read inspection_state"  on public.inspection_state;
drop policy if exists "anon write inspection_state" on public.inspection_state;
drop policy if exists "anon read team_members"      on public.team_members;
drop policy if exists "anon write team_members"     on public.team_members;
drop policy if exists "anon read app_meta"          on public.app_meta;
drop policy if exists "anon write app_meta"         on public.app_meta;

create policy "anon read rule_state"       on public.rule_state       for select to anon using (true);
create policy "anon write rule_state"       on public.rule_state       for insert to anon with check (true);
create policy "anon update rule_state"       on public.rule_state       for update to anon using (true) with check (true);
create policy "anon delete rule_state"       on public.rule_state       for delete to anon using (true);

create policy "anon read inspection_state"  on public.inspection_state  for select to anon using (true);
create policy "anon write inspection_state"  on public.inspection_state  for insert to anon with check (true);
create policy "anon update inspection_state" on public.inspection_state  for update to anon using (true) with check (true);
create policy "anon delete inspection_state" on public.inspection_state  for delete to anon using (true);

create policy "anon read team_members"      on public.team_members      for select to anon using (true);
create policy "anon write team_members"      on public.team_members      for insert to anon with check (true);
create policy "anon update team_members"      on public.team_members      for update to anon using (true) with check (true);
create policy "anon delete team_members"      on public.team_members      for delete to anon using (true);

create policy "anon read app_meta"          on public.app_meta          for select to anon using (true);
create policy "anon write app_meta"          on public.app_meta          for insert to anon with check (true);
create policy "anon update app_meta"          on public.app_meta          for update to anon using (true) with check (true);
create policy "anon delete app_meta"          on public.app_meta          for delete to anon using (true);

-- ── Keep updated_at honest ──────────────────────────────────────────────────
-- The client sets updated_at explicitly so that offline-queued writes keep
-- their original timestamp; this trigger is a safety net for direct SQL use.
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists rule_state_touch       on public.rule_state;
drop trigger if exists inspection_state_touch on public.inspection_state;
drop trigger if exists app_meta_touch         on public.app_meta;

create trigger rule_state_touch       before update on public.rule_state
  for each row execute function public.touch_updated_at();
create trigger inspection_state_touch before update on public.inspection_state
  for each row execute function public.touch_updated_at();
create trigger app_meta_touch         before update on public.app_meta
  for each row execute function public.touch_updated_at();
