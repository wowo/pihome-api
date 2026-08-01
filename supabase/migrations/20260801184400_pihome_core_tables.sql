-- Applied via MCP to project agxpttxixydvttjnxhbn (pihome)
create table public.switch_events (
  id uuid primary key default gen_random_uuid(),
  date timestamptz not null default now(),
  switch text not null,
  state text not null,
  user_email text
);
create index switch_events_date_idx on public.switch_events (date desc);

create table public.switch_state (
  key text primary key,
  state text,
  scheduled jsonb,
  updated_at timestamptz not null default now(),
  name text,
  type text,
  stateless boolean default false,
  durations jsonb
);

create table public.readings (
  id uuid primary key default gen_random_uuid(),
  date timestamptz not null,
  sensor_key text not null,
  value numeric not null,
  kind text not null
);
create index readings_date_idx on public.readings (date desc);
create index readings_sensor_date_idx on public.readings (sensor_key, date desc);

alter table public.switch_events enable row level security;
alter table public.switch_state enable row level security;
alter table public.readings enable row level security;

create policy "authenticated read switch_events"
  on public.switch_events for select to authenticated using (true);
create policy "authenticated read switch_state"
  on public.switch_state for select to authenticated using (true);
create policy "authenticated read readings"
  on public.readings for select to authenticated using (true);

grant select on public.switch_events, public.switch_state, public.readings to authenticated;
grant all on public.switch_events, public.switch_state, public.readings to service_role;

alter publication supabase_realtime add table public.switch_state;
