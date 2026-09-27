-- Chitrak checklist — paste the WHOLE block into Supabase SQL Editor and Run.
-- Idempotent: safe to run more than once.

-- ── Tables ────────────────────────────────────────────────────────────────────
-- Only mutable state lives here. Rule text, codes and titles for all 239 items
-- ship inside the HTML file; the database stores completion, notes and stamps.

create table if not exists public.rule_state (
  rule_id      text primary key,
  completed    boolean not null default false,
  note         text    not null default '',
  completed_at timestamptz,
  updated_at   timestamptz not null default now()
);

create table if not exists public.inspection_state (
  item_id      text primary key,
  completed    boolean not null default false,
  note         text    not null default '',
  completed_at timestamptz,
  updated_at   timestamptz not null default now()
);

create table if not exists public.team_members (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  role       text not null default '',
  created_at timestamptz not null default now()
);

create table if not exists public.app_meta (
  key        text primary key,
  value      jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists rule_state_updated_idx       on public.rule_state (updated_at);
create index if not exists inspection_state_updated_idx on public.inspection_state (updated_at);
create index if not exists team_members_created_idx     on public.team_members (created_at);

-- ── updated_at trigger ────────────────────────────────────────────────────────
-- The client sets updated_at explicitly so offline-queued writes keep their
-- original timestamp; this is a safety net for direct SQL use.

create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

do $$
declare t text;
begin
  foreach t in array array['rule_state', 'inspection_state', 'app_meta'] loop
    execute format('drop trigger if exists %I on public.%I', t || '_touch', t);
    execute format('create trigger %I before update on public.%I for each row execute function public.touch_updated_at()', t || '_touch', t);
  end loop;
end $$;

-- ── Row Level Security ────────────────────────────────────────────────────────
-- Enabled now so adding Supabase Auth later is a policy swap, not a rewrite.
-- These policies let the `anon` role read and write, which is what makes the
-- MVP work with just the anon public key. Anyone holding the URL can therefore
-- edit the checklist — see SETUP.md -> "Adding authentication" before that
-- matters for you.

do $$
declare tbl text;
begin
  foreach tbl in array array['rule_state', 'inspection_state', 'team_members', 'app_meta'] loop
    execute format('alter table public.%I enable row level security', tbl);

    execute format('drop policy if exists %I on public.%I', 'anon_select_' || tbl, tbl);
    execute format('create policy %I on public.%I for select to anon using (true)', 'anon_select_' || tbl, tbl);

    execute format('drop policy if exists %I on public.%I', 'anon_insert_' || tbl, tbl);
    execute format('create policy %I on public.%I for insert to anon with check (true)', 'anon_insert_' || tbl, tbl);

    execute format('drop policy if exists %I on public.%I', 'anon_update_' || tbl, tbl);
    execute format('create policy %I on public.%I for update to anon using (true) with check (true)', 'anon_update_' || tbl, tbl);

    execute format('drop policy if exists %I on public.%I', 'anon_delete_' || tbl, tbl);
    execute format('create policy %I on public.%I for delete to anon using (true)', 'anon_delete_' || tbl, tbl);
  end loop;
end $$;

-- ── Verify (optional) ─────────────────────────────────────────────────────────
-- select table_name, (select count(*) from information_schema.policies p
--                     where p.table_name = t.table_name) as policies
-- from information_schema.tables t
-- where table_schema = 'public' order by table_name;
