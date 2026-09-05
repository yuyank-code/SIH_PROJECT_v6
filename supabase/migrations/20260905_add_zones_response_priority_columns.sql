-- Fixes schema drift: risk_service.py, supabase_db.py, and supabase_repo.py
-- all read/write these three columns on `zones` for response-priority scoring
-- (road access, village isolation, recent field reports), but no prior
-- migration ever added them, causing:
--   postgrest.exceptions.APIError: column zones_1.road_blocked does not exist
-- on every call to get_predictions() / dashboard_summary() / response_priorities().
--
-- NOTE: this was already run directly against the live Supabase project via
-- the SQL Editor on 2026-09-05. This file exists so a fresh/future Supabase
-- project built from this repo has the columns from the start.

alter table public.zones
    add column if not exists road_blocked boolean not null default false,
    add column if not exists isolated_villages integer not null default 0,
    add column if not exists recent_field_report boolean not null default false;
