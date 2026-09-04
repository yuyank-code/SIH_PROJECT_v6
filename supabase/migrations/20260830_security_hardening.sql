-- SIH Project: Supabase security hardening
-- Applied to the connected Supabase project on 2026-08-30.
--
-- This migration records the production security changes made during the
-- Supabase migration phase. It is intentionally idempotent where practical.

begin;

-- SECURITY DEFINER helpers are restricted to signed-in users. These helpers
-- read the caller's profile and are used by RLS policies.
revoke execute on function public.current_user_role() from public;
revoke execute on function public.is_authority() from public;
grant execute on function public.current_user_role() to authenticated;
grant execute on function public.is_authority() to authenticated;

-- Pin the search path for SECURITY DEFINER helpers.
alter function public.current_user_role() set search_path = public;
alter function public.is_authority() set search_path = public;

-- Trigger helper search path is also pinned.
alter function public.handle_new_user() set search_path = public;
alter function public.set_updated_at() set search_path = public;

-- RLS is required for recipient records. Recipients are intended for
-- authority-side management and must not be exposed to anonymous callers.
alter table public.recipients enable row level security;
drop policy if exists recipients_authenticated_select on public.recipients;
drop policy if exists recipients_authority_write on public.recipients;
create policy recipients_authenticated_select
  on public.recipients
  for select
  to authenticated
  using (is_authority());
create policy recipients_authority_write
  on public.recipients
  for all
  to authenticated
  using (is_authority())
  with check (is_authority());

commit;
