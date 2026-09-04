-- =============================================================================
-- NER-SLIDE — Base schema (reproducible)
-- =============================================================================
-- Reconstructed on 2026-08-31 from what the backend code actually reads and
-- writes (backend/app/db/supabase_repo.py, migration_seed.py, auth_service.py,
-- device_service.py, and the RLS policies in supabase/migrations/*.sql).
--
-- WHY THIS FILE EXISTS
--   The repo's supabase/migrations/ folder only contained RLS policies, indexes
--   and grants — never any CREATE TABLE / CREATE FUNCTION. The live tables and
--   PostGIS RPCs were built in the Supabase dashboard, so a fresh project could
--   not be recreated from the repo. This file closes that gap.
--
-- ORDER OF EXECUTION for a brand-new Supabase project:
--   1. This file  (schema.sql)          -> extensions, tables, functions, RPCs
--   2. migrations/20260830_security_hardening.sql
--   3. migrations/20260830_rls_policy_consolidation_v3.sql
--   4. migrations/20260830_security_performance_hardening_v2.sql
--   5. migrations/20260830_response_tasks_policy_cleanup_v4.sql
--   6. migrations/20260831_grant_gis_access_to_backend_service_role.sql
--   7. (optional) seed data:  python -m app.db.migration_seed
--
-- NOTE: This is a faithful reconstruction, not a dump of your live database. If
-- you already have a working Supabase project, diff this against it before
-- running anything — do not run it blindly against production data. It is
-- idempotent (IF NOT EXISTS / OR REPLACE) and safe to run on an empty project.
-- =============================================================================

begin;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists "postgis";    -- geography/geometry + distance

-- ---------------------------------------------------------------------------
-- Enums (kept as CHECK constraints below rather than TYPEs, so values can be
-- adjusted without ALTER TYPE gymnastics). Allowed values are documented inline.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- Core geospatial reference tables
-- ===========================================================================

-- Risk zones (22 in the NER seed). PostgREST exposes this as .table("zones").
create table if not exists public.zones (
    id             uuid primary key default gen_random_uuid(),
    zone_id        text unique not null,                     -- stable app id, e.g. "NER-001"
    name           text not null,
    district       text,
    state          text,
    population      integer,
    terrain_source text default 'DEMO',                      -- DEMO | DEM | ...
    -- V5 terrain features (persisted per zone; feed the model 1:1)
    elevation_m    double precision,
    slope_deg      double precision,
    aspect_sin     double precision,
    aspect_cos     double precision,
    curvature_1_m  double precision,
    centroid       geography(Point, 4326),                   -- written as WKT POINT(lon lat)
    boundary       geography(Polygon, 4326),                 -- written as WKT POLYGON((...))
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
create index if not exists zones_centroid_gix on public.zones using gist (centroid);
create index if not exists zones_boundary_gix on public.zones using gist (boundary);

-- Field sensors (rain gauges, tiltmeters, etc.).
create table if not exists public.sensors (
    id           uuid primary key default gen_random_uuid(),
    sensor_id    text unique not null,
    zone_id      uuid references public.zones(id) on delete set null,
    sensor_type  text not null default 'unknown',
    status       text not null default 'OFFLINE',            -- ONLINE | OFFLINE
    location     geography(Point, 4326),
    metadata     jsonb not null default '{}'::jsonb,         -- battery, source, ...
    last_seen_at timestamptz,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
create index if not exists sensors_zone_id_idx on public.sensors(zone_id);
create index if not exists sensors_location_gix on public.sensors using gist (location);

-- Road network segments.
create table if not exists public.roads (
    id         uuid primary key default gen_random_uuid(),
    road_id    text unique not null,
    name       text,
    status     text not null default 'UNKNOWN'
               check (status in ('OPEN','BLOCKED','RESTRICTED','UNKNOWN')),
    geometry   geography(LineString, 4326),
    metadata   jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists roads_geometry_gix on public.roads using gist (geometry);

-- Villages / settlements.
create table if not exists public.villages (
    id         uuid primary key default gen_random_uuid(),
    village_id text unique not null,
    name       text not null,
    state      text,
    population integer,
    location   geography(Point, 4326),
    metadata   jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists villages_location_gix on public.villages using gist (location);

-- Per-zone terrain snapshot recomputed from a DEM (POST /api/terrain/recompute).
create table if not exists public.terrain_data (
    id            uuid primary key default gen_random_uuid(),
    zone_id       uuid unique references public.zones(id) on delete cascade,
    elevation_m   double precision,
    slope_deg     double precision,
    aspect_sin    double precision,
    aspect_cos    double precision,
    curvature_1_m double precision,
    source        text default 'DEM',
    fetched_at    timestamptz not null default now()
);

-- ===========================================================================
-- Identity & auth
-- ===========================================================================

-- Application profile, 1:1 with auth.users. Role drives all authorization.
create table if not exists public.profiles (
    id         uuid primary key references auth.users(id) on delete cascade,
    full_name  text,
    phone      text,
    role       text not null default 'CITIZEN'
               check (role in ('CITIZEN','FIELD_OFFICER','AUTHORITY','ADMIN')),
    is_active  boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Registered devices for FCM push (register_device RPC upserts here).
create table if not exists public.user_devices (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid references auth.users(id) on delete cascade,
    fcm_token  text unique not null,
    platform   text,                                         -- android | ios | web
    is_active  boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists user_devices_user_id_idx on public.user_devices(user_id);

-- ===========================================================================
-- Operational data
-- ===========================================================================

-- Sensor time-series readings.
create table if not exists public.sensor_readings (
    id               uuid primary key default gen_random_uuid(),
    sensor_id        uuid references public.sensors(id) on delete cascade,
    measurement_type text not null,                          -- rainfall | tilt | ...
    value            double precision not null,
    recorded_at      timestamptz not null default now(),
    created_at       timestamptz not null default now()
);
create index if not exists sensor_readings_sensor_id_idx on public.sensor_readings(sensor_id);

-- Citizen / field reports. client_uuid gives offline-first idempotency.
--   A report is ground truth *claimed* by a person, not ground truth confirmed.
--   The triage columns (v5) record who checked it and what they concluded, so a
--   raw claim is never silently promoted to fact.
create table if not exists public.reports (
    id                uuid primary key default gen_random_uuid(),
    client_uuid       text unique,
    reporter_id       uuid references auth.users(id) on delete set null,
    reporter_role     text default 'CITIZEN',
    lat               double precision not null,
    lon               double precision not null,
    report_type       text not null,                         -- ROAD_BLOCKAGE | ...
    description       text default '',
    status            text not null default 'SUBMITTED',     -- see triage check below
    nearest_zone_id   uuid references public.zones(id) on delete set null,
    -- v5 triage
    verified_by       uuid references auth.users(id) on delete set null,
    verified_at       timestamptz,
    verification_note text default '',
    incident_id       uuid,                                  -- FK added after public.incidents exists
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create index if not exists reports_reporter_id_idx on public.reports(reporter_id);
create index if not exists reports_nearest_zone_id_idx on public.reports(nearest_zone_id);

-- v5 triage columns, added separately so installs created before v5 upgrade
-- cleanly. (public.incidents is created further down; the FK is attached in the
-- backfill block at the end of this file, after that table exists.)
alter table public.reports add column if not exists verified_by       uuid;
alter table public.reports add column if not exists verified_at       timestamptz;
alter table public.reports add column if not exists verification_note text default '';
alter table public.reports add column if not exists incident_id       uuid;
alter table public.reports add column if not exists updated_at        timestamptz not null default now();
create index if not exists reports_status_idx on public.reports(status);
create index if not exists reports_incident_id_idx on public.reports(incident_id);
create index if not exists reports_created_at_idx on public.reports(created_at desc);

-- Constrain the triage vocabulary. `add constraint if not exists` does not exist
-- in PostgreSQL, so guard on the catalogue to stay re-runnable.
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'reports_status_check') then
        alter table public.reports add constraint reports_status_check
            check (status in ('SUBMITTED','VERIFIED','REJECTED','DUPLICATE','ACTIONED'));
    end if;
end
$$;

-- Media attached to a report (stored in the report-media storage bucket).
create table if not exists public.report_media (
    id           uuid primary key default gen_random_uuid(),
    report_id    uuid references public.reports(id) on delete cascade,
    storage_path text not null,
    media_type   text default 'PHOTO',
    mime_type    text,
    size_bytes   bigint,
    created_at   timestamptz not null default now()
);
create index if not exists report_media_report_id_idx on public.report_media(report_id);

-- Latest model output per zone. UNIQUE(zone_id) supports upsert on_conflict=zone_id.
create table if not exists public.risk_predictions (
    id                   uuid primary key default gen_random_uuid(),
    zone_id              uuid unique references public.zones(id) on delete cascade,
    probability          double precision,
    risk_score           double precision,
    prediction           integer,                            -- 0/1 at the 0.15 threshold
    severity             text,                               -- LOW|MEDIUM|HIGH|CRITICAL
    priority             text,                               -- P1..P4
    model_version        text,
    features_used        jsonb not null default '{}'::jsonb,
    contributing_factors jsonb not null default '[]'::jsonb,
    source_map           jsonb not null default '{}'::jsonb,
    predicted_at         timestamptz not null default now(),
    created_at           timestamptz not null default now()
);

-- Multilingual alerts. translations holds {lang: text, ..., "_sources": {...}}.
create table if not exists public.alerts (
    id                 uuid primary key default gen_random_uuid(),
    zone_id            uuid references public.zones(id) on delete cascade,
    severity           text not null,
    reason             text,
    recommended_action text,
    translations       jsonb not null default '{}'::jsonb,   -- incl. _sources provenance
    status             text not null default 'ACTIVE',
    created_by         uuid references auth.users(id) on delete set null,
    created_at         timestamptz not null default now()
);
create index if not exists alerts_created_by_idx on public.alerts(created_by);
create index if not exists alerts_zone_id_idx on public.alerts(zone_id);

-- Push/SMS delivery log.
create table if not exists public.notifications (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid references auth.users(id) on delete set null,
    alert_id   uuid references public.alerts(id) on delete cascade,
    channel    text not null default 'PUSH',
    status     text not null,                                -- SENT | FAILED
    provider   text,                                         -- FCM_HTTP_V1 | ...
    payload    jsonb not null default '{}'::jsonb,
    sent_at    timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists notifications_alert_id_idx on public.notifications(alert_id);

-- Alert broadcast recipients (authority-managed contact list).
create table if not exists public.recipients (
    id         uuid primary key default gen_random_uuid(),
    name       text not null,
    phone      text not null,
    role       text not null default 'AUTHORITY',
    district   text,
    language   text not null default 'en',
    created_at timestamptz not null default now()
);

-- Human feedback on predictions (ground truth for retraining).
create table if not exists public.model_feedback (
    id            uuid primary key default gen_random_uuid(),
    zone_id       uuid references public.zones(id) on delete cascade,
    prediction_id uuid references public.risk_predictions(id) on delete set null,
    label         text not null,                             -- e.g. TRUE_POSITIVE
    notes         text default '',
    created_by    uuid references auth.users(id) on delete set null,
    created_at    timestamptz not null default now()
);
create index if not exists model_feedback_zone_id_idx on public.model_feedback(zone_id);
create index if not exists model_feedback_prediction_id_idx on public.model_feedback(prediction_id);
create index if not exists model_feedback_created_by_idx on public.model_feedback(created_by);

-- Response task board (referenced by RLS policies; assignee can update own rows).
create table if not exists public.response_tasks (
    id          uuid primary key default gen_random_uuid(),
    zone_id     uuid references public.zones(id) on delete cascade,
    title       text,
    description text,
    status      text not null default 'OPEN',
    priority    text,
    assigned_to uuid references auth.users(id) on delete set null,
    created_by  uuid references auth.users(id) on delete set null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists response_tasks_zone_id_idx on public.response_tasks(zone_id);
create index if not exists response_tasks_created_by_idx on public.response_tasks(created_by);

-- Satellite imagery references (referenced by a hardening index; optional feature).
create table if not exists public.satellite_data (
    id         uuid primary key default gen_random_uuid(),
    zone_id    uuid references public.zones(id) on delete cascade,
    source     text default 'COPERNICUS',
    captured_at timestamptz,
    metadata   jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists satellite_data_zone_id_idx on public.satellite_data(zone_id);

-- ===========================================================================
-- Response & Recovery extension (added 2026-08-31)
--   Powers dispatch & routing (Feature A), the live ops feed (Feature B) and the
--   post-landslide recovery module (Feature D). response_tasks is reused for both
--   response and recovery work via a `phase` flag, so there is one task board.
--   Everything carries a `source` column — the project's "never fabricate; every
--   payload is provenance-tagged" rule extends to the response/recovery half too.
-- ===========================================================================

-- Extend the response_tasks board for dispatch + routing + recovery reuse.
-- Idempotent: safe whether the table was just created above or already exists in
-- a live project. No existing data is dropped or rewritten.
alter table public.response_tasks add column if not exists phase       text not null default 'RESPONSE';  -- RESPONSE | RECOVERY
alter table public.response_tasks add column if not exists team        text;                               -- assigned unit / team name (free text)
alter table public.response_tasks add column if not exists route       jsonb not null default '{}'::jsonb; -- nearest roads + blocked-segment flags captured at dispatch
alter table public.response_tasks add column if not exists incident_id uuid;                                -- soft link to incidents(id) for recovery tasks
alter table public.response_tasks add column if not exists source      text default 'AUTHORITY';           -- provenance of the task
alter table public.response_tasks add column if not exists resolved_at timestamptz;
create index if not exists response_tasks_incident_id_idx on public.response_tasks(incident_id);
create index if not exists response_tasks_phase_idx on public.response_tasks(phase);

-- A confirmed landslide event. Created when field evidence confirms an incident,
-- so the platform can flip a zone from "predicted risk" into "active response".
create table if not exists public.incidents (
    id           uuid primary key default gen_random_uuid(),
    zone_id      uuid references public.zones(id) on delete set null,
    title        text not null,
    status       text not null default 'ACTIVE'
                 check (status in ('ACTIVE','CONTAINED','CLOSED')),
    severity     text,                                       -- LOW|MEDIUM|HIGH|CRITICAL (snapshot at confirmation)
    occurred_at  timestamptz,
    summary      text default '',
    source       text not null default 'FIELD_CONFIRMED',    -- provenance (never fabricated)
    confirmed_by uuid references auth.users(id) on delete set null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
create index if not exists incidents_zone_id_idx on public.incidents(zone_id);
create index if not exists incidents_status_idx on public.incidents(status);

-- Per-village impact / needs assessment for an incident. One row per affected
-- village. Count columns are nullable and default to NULL (= "not yet assessed"),
-- deliberately NOT 0 — a zero would be a fabricated assessment.
create table if not exists public.incident_impacts (
    id                  uuid primary key default gen_random_uuid(),
    incident_id         uuid references public.incidents(id) on delete cascade,
    village_id          uuid references public.villages(id) on delete set null,
    village_name        text,                                -- snapshot label (survives village edits)
    affected_population integer,
    households          integer,
    casualties          integer,
    injured             integer,
    status              text not null default 'ASSESSING'
                        check (status in ('ASSESSING','PARTIAL','ASSESSED')),
    needs               jsonb not null default '{}'::jsonb,  -- {shelter:true, medical:true, food:true, ...}
    notes               text default '',
    source              text not null default 'FIELD_REPORT',
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);
create index if not exists incident_impacts_incident_id_idx on public.incident_impacts(incident_id);
create index if not exists incident_impacts_village_id_idx on public.incident_impacts(village_id);

-- Relief-resource tracking for an incident (shelter, food, medical, ...).
create table if not exists public.relief_resources (
    id            uuid primary key default gen_random_uuid(),
    incident_id   uuid references public.incidents(id) on delete cascade,
    resource_type text not null
                  check (resource_type in ('SHELTER','FOOD','WATER','MEDICAL','RESCUE_TEAM','LOGISTICS','OTHER')),
    label         text,
    quantity      numeric,
    unit          text,
    status        text not null default 'REQUESTED'
                  check (status in ('REQUESTED','ALLOCATED','IN_TRANSIT','DELIVERED')),
    source        text not null default 'AUTHORITY',
    notes         text default '',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
create index if not exists relief_resources_incident_id_idx on public.relief_resources(incident_id);

-- Recovery playbook (Feature F, added 2026-09-01).
--   A phased recovery plan per incident, and its checklist of recovery steps.
--   Steps are copied from a standard NDMA/Sphere-aligned template (source=TEMPLATE)
--   and worked through; authorities/field officers may add their own (source=MANUAL).
--   One plan per incident (unique incident_id). Idempotent create.
create table if not exists public.recovery_plans (
    id          uuid primary key default gen_random_uuid(),
    incident_id uuid not null unique references public.incidents(id) on delete cascade,
    framework   text not null default 'NDMA/Sphere-aligned landslide recovery checklist (adapted for NER)',
    status      text not null default 'ACTIVE'
                check (status in ('ACTIVE','COMPLETE')),
    created_by  uuid references auth.users(id) on delete set null,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists recovery_plans_incident_id_idx on public.recovery_plans(incident_id);

create table if not exists public.recovery_steps (
    id          uuid primary key default gen_random_uuid(),
    plan_id     uuid not null references public.recovery_plans(id) on delete cascade,
    code        text not null,                               -- template code (e.g. REL-SAR) or MANUAL-xxxx
    phase       text not null
                check (phase in ('RELIEF','EARLY_RECOVERY','RESTORATION','RESILIENCE')),
    title       text not null,
    detail      text default '',
    status      text not null default 'PENDING'
                check (status in ('PENDING','IN_PROGRESS','DONE','NA')),  -- NA = does not apply to this event
    owner       text,                                        -- assigned team / person (free text)
    notes       text default '',
    due_at      timestamptz,
    done_at     timestamptz,
    phase_order integer not null default 0,                  -- stable ordering across phases
    step_order  integer not null default 0,                  -- stable ordering within a phase
    requires_assessment boolean not null default false,      -- true = must be confirmed on the ground before DONE
    manageable_when text default '',                         -- human-readable gate: when this step becomes possible
    source      text not null default 'TEMPLATE',            -- TEMPLATE | MANUAL (provenance)
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (plan_id, code)                                   -- a template code appears once per plan (idempotent generate)
);
create index if not exists recovery_steps_plan_id_idx on public.recovery_steps(plan_id);
create index if not exists recovery_steps_status_idx on public.recovery_steps(status);
-- guidance columns for installs created before v4 (idempotent)
alter table public.recovery_steps add column if not exists requires_assessment boolean not null default false;
alter table public.recovery_steps add column if not exists manageable_when    text default '';

-- Now that public.incidents exists, attach the reports -> incidents FK declared
-- earlier as a bare uuid. Guarded on the catalogue so this stays re-runnable.
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'reports_incident_id_fkey') then
        alter table public.reports add constraint reports_incident_id_fkey
            foreign key (incident_id) references public.incidents(id) on delete set null;
    end if;
    if not exists (select 1 from pg_constraint where conname = 'reports_verified_by_fkey') then
        alter table public.reports add constraint reports_verified_by_fkey
            foreign key (verified_by) references auth.users(id) on delete set null;
    end if;
end
$$;

-- ---------------------------------------------------------------------------
-- Shelters (Feature K, added 2026-09-03).
--   A located, capacity-tracked place a person can actually be sent to.
--   Distinct from relief_resources.resource_type='SHELTER', which is an
--   incident-scoped supply line item with no coordinates and no occupancy —
--   useful for logistics, useless for answering "where do I go?".
--   `source` records provenance for every row (SEED_DEMO for the bundled demo
--   set, AUTHORITY for rows entered by a district officer). Nothing here should
--   be read as an authoritative government shelter list unless source says so.
-- ---------------------------------------------------------------------------
create table if not exists public.shelters (
    id                uuid primary key default gen_random_uuid(),
    shelter_id        text unique not null,                  -- stable app id, e.g. "SHL-001"
    name              text not null,
    category          text not null default 'OTHER'
                      check (category in ('RELIEF_CAMP','SCHOOL','COMMUNITY_HALL','HOSPITAL','HELIPAD','OTHER')),
    location          geography(Point, 4326),
    elevation_m       double precision,                      -- used to prefer higher ground; null = unknown
    capacity          integer,                               -- null = capacity not recorded, never assume 0
    current_occupancy integer,                               -- null = not counted, never assume empty
    status            text not null default 'OPEN'
                      check (status in ('OPEN','FULL','CLOSED','STANDBY')),
    contact_phone     text,
    managed_by        text,
    district          text,
    state             text,
    source            text not null default 'AUTHORITY',     -- SEED_DEMO | AUTHORITY | ...
    verified_at       timestamptz,                           -- last time a human confirmed this record
    metadata          jsonb not null default '{}'::jsonb,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create index if not exists shelters_location_gix on public.shelters using gist (location);
create index if not exists shelters_status_idx on public.shelters(status);

-- ===========================================================================
-- Auth helper functions (used by RLS policies in the migration files)
-- ===========================================================================

-- Caller's application role, read from their profile (never from client input).
create or replace function public.current_user_role()
returns text
language sql
stable
security definer
set search_path = public
as $$
    select role from public.profiles where id = auth.uid();
$$;

-- Convenience predicate: is the caller an ADMIN or AUTHORITY?
create or replace function public.is_authority()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(public.current_user_role() in ('ADMIN','AUTHORITY'), false);
$$;

-- Auto-provision a profile row when a new auth user signs up.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, full_name, phone, role, is_active)
    values (
        new.id,
        new.raw_user_meta_data->>'full_name',
        new.raw_user_meta_data->>'phone',
        'CITIZEN',
        true
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

-- Generic updated_at touch trigger.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- Wire the new-user trigger to Supabase auth.
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Keep updated_at fresh on the tables that expose it.
drop trigger if exists set_zones_updated_at on public.zones;
create trigger set_zones_updated_at before update on public.zones
    for each row execute function public.set_updated_at();
drop trigger if exists set_sensors_updated_at on public.sensors;
create trigger set_sensors_updated_at before update on public.sensors
    for each row execute function public.set_updated_at();
drop trigger if exists set_roads_updated_at on public.roads;
create trigger set_roads_updated_at before update on public.roads
    for each row execute function public.set_updated_at();
drop trigger if exists set_villages_updated_at on public.villages;
create trigger set_villages_updated_at before update on public.villages
    for each row execute function public.set_updated_at();
drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at before update on public.profiles
    for each row execute function public.set_updated_at();
drop trigger if exists set_user_devices_updated_at on public.user_devices;
create trigger set_user_devices_updated_at before update on public.user_devices
    for each row execute function public.set_updated_at();
drop trigger if exists set_response_tasks_updated_at on public.response_tasks;
create trigger set_response_tasks_updated_at before update on public.response_tasks
    for each row execute function public.set_updated_at();
drop trigger if exists set_incidents_updated_at on public.incidents;
create trigger set_incidents_updated_at before update on public.incidents
    for each row execute function public.set_updated_at();
drop trigger if exists set_incident_impacts_updated_at on public.incident_impacts;
create trigger set_incident_impacts_updated_at before update on public.incident_impacts
    for each row execute function public.set_updated_at();
drop trigger if exists set_relief_resources_updated_at on public.relief_resources;
create trigger set_relief_resources_updated_at before update on public.relief_resources
    for each row execute function public.set_updated_at();
drop trigger if exists set_recovery_plans_updated_at on public.recovery_plans;
create trigger set_recovery_plans_updated_at before update on public.recovery_plans
    for each row execute function public.set_updated_at();
drop trigger if exists set_recovery_steps_updated_at on public.recovery_steps;
create trigger set_recovery_steps_updated_at before update on public.recovery_steps
    for each row execute function public.set_updated_at();
drop trigger if exists set_shelters_updated_at on public.shelters;
create trigger set_shelters_updated_at before update on public.shelters
    for each row execute function public.set_updated_at();
drop trigger if exists set_reports_updated_at on public.reports;
create trigger set_reports_updated_at before update on public.reports
    for each row execute function public.set_updated_at();

-- ===========================================================================
-- RPCs consumed by the backend (names/args/return shapes match supabase_repo.py)
-- ===========================================================================
-- The Python layer expects:
--   * centroid returned as JSON {"lat":..,"lon":..}
--   * geometry/boundary returned as GeoJSON (used directly in FeatureCollections)
--   * sensor points projected to lat/lon columns
-- These helpers do exactly that so the repo mappers work unchanged.

-- Internal helper: zone row shaped exactly as _zone() in supabase_repo.py expects.
create or replace function public.list_zones_geojson(p_state text default null)
returns table (
    id uuid, zone_id text, name text, district text, state text,
    population integer, terrain_source text,
    elevation_m double precision, slope_deg double precision,
    aspect_sin double precision, aspect_cos double precision, curvature_1_m double precision,
    centroid jsonb, geometry jsonb,
    created_at timestamptz, updated_at timestamptz
)
language sql
stable
as $$
    select z.id, z.zone_id, z.name, z.district, z.state,
           z.population, z.terrain_source,
           z.elevation_m, z.slope_deg, z.aspect_sin, z.aspect_cos, z.curvature_1_m,
           jsonb_build_object(
               'lat', st_y(z.centroid::geometry),
               'lon', st_x(z.centroid::geometry)
           ) as centroid,
           st_asgeojson(z.boundary)::jsonb as geometry,
           z.created_at, z.updated_at
    from public.zones z
    where p_state is null or z.state = p_state
    order by z.zone_id;
$$;

create or replace function public.get_zone_geojson(p_zone_id text)
returns table (
    id uuid, zone_id text, name text, district text, state text,
    population integer, terrain_source text,
    elevation_m double precision, slope_deg double precision,
    aspect_sin double precision, aspect_cos double precision, curvature_1_m double precision,
    centroid jsonb, geometry jsonb,
    created_at timestamptz, updated_at timestamptz
)
language sql
stable
as $$
    select z.id, z.zone_id, z.name, z.district, z.state,
           z.population, z.terrain_source,
           z.elevation_m, z.slope_deg, z.aspect_sin, z.aspect_cos, z.curvature_1_m,
           jsonb_build_object(
               'lat', st_y(z.centroid::geometry),
               'lon', st_x(z.centroid::geometry)
           ) as centroid,
           st_asgeojson(z.boundary)::jsonb as geometry,
           z.created_at, z.updated_at
    from public.zones z
    where z.zone_id = p_zone_id;
$$;

create or replace function public.list_roads_geojson()
returns table (
    road_id text, name text, status text, geometry jsonb
)
language sql
stable
as $$
    select r.road_id, r.name, r.status, st_asgeojson(r.geometry)::jsonb as geometry
    from public.roads r
    order by r.road_id;
$$;

create or replace function public.list_villages_geojson()
returns table (
    village_id text, name text, state text, population integer,
    lat double precision, lon double precision
)
language sql
stable
as $$
    select v.village_id, v.name, v.state, v.population,
           st_y(v.location::geometry) as lat,
           st_x(v.location::geometry) as lon
    from public.villages v
    order by v.village_id;
$$;

create or replace function public.list_sensors_geojson(p_status text default null)
returns table (
    sensor_id text, zone_id text, sensor_type text, status text,
    lat double precision, lon double precision,
    metadata jsonb, last_seen_at timestamptz
)
language sql
stable
as $$
    select s.sensor_id,
           z.zone_id,
           s.sensor_type, s.status,
           st_y(s.location::geometry) as lat,
           st_x(s.location::geometry) as lon,
           s.metadata, s.last_seen_at
    from public.sensors s
    left join public.zones z on z.id = s.zone_id
    where p_status is null or s.status = p_status
    order by s.sensor_id;
$$;

create or replace function public.nearby_roads(p_lat double precision, p_lon double precision, p_limit integer default 3)
returns table (
    road_id text, name text, status text, geometry jsonb, distance_km double precision
)
language sql
stable
as $$
    select r.road_id, r.name, r.status,
           st_asgeojson(r.geometry)::jsonb as geometry,
           st_distance(
               r.geometry,
               st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography
           ) / 1000.0 as distance_km
    from public.roads r
    where r.geometry is not null
    order by r.geometry <-> st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography
    limit greatest(p_limit, 0);
$$;

create or replace function public.nearby_villages(p_lat double precision, p_lon double precision, p_limit integer default 3)
returns table (
    village_id text, name text, state text, population integer,
    lat double precision, lon double precision, distance_km double precision
)
language sql
stable
as $$
    select v.village_id, v.name, v.state, v.population,
           st_y(v.location::geometry) as lat,
           st_x(v.location::geometry) as lon,
           st_distance(
               v.location,
               st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography
           ) / 1000.0 as distance_km
    from public.villages v
    where v.location is not null
    order by v.location <-> st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography
    limit greatest(p_limit, 0);
$$;

-- Nearest shelters to a point, with straight-line distance. Ordering and
-- distance are PostGIS facts; the *ranking* (capacity, status, slope risk) is
-- deliberately left to the application layer so its reasoning stays inspectable.
create or replace function public.nearby_shelters(p_lat double precision, p_lon double precision, p_limit integer default 5)
returns table (
    shelter_id text, name text, category text, status text,
    capacity integer, current_occupancy integer, contact_phone text,
    managed_by text, district text, state text, elevation_m double precision,
    source text, lat double precision, lon double precision, distance_km double precision
)
language sql
stable
as $$
    select s.shelter_id, s.name, s.category, s.status,
           s.capacity, s.current_occupancy, s.contact_phone,
           s.managed_by, s.district, s.state, s.elevation_m, s.source,
           st_y(s.location::geometry) as lat,
           st_x(s.location::geometry) as lon,
           st_distance(
               s.location,
               st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography
           ) / 1000.0 as distance_km
    from public.shelters s
    where s.location is not null
    order by s.location <-> st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography
    limit greatest(p_limit, 0);
$$;

-- Every shelter as GeoJSON for the map layer.
create or replace function public.list_shelters_geojson()
returns table (
    shelter_id text, name text, category text, status text,
    capacity integer, current_occupancy integer, district text, state text,
    source text, lat double precision, lon double precision
)
language sql
stable
as $$
    select s.shelter_id, s.name, s.category, s.status,
           s.capacity, s.current_occupancy, s.district, s.state, s.source,
           st_y(s.location::geometry) as lat,
           st_x(s.location::geometry) as lon
    from public.shelters s
    where s.location is not null
    order by s.shelter_id;
$$;

-- Register (or reactivate) the caller's device token for push.
create or replace function public.register_device(p_fcm_token text, p_platform text)
returns public.user_devices
language plpgsql
security definer
set search_path = public
as $$
declare
    result public.user_devices;
begin
    insert into public.user_devices (user_id, fcm_token, platform, is_active)
    values (auth.uid(), p_fcm_token, p_platform, true)
    on conflict (fcm_token) do update
        set user_id = excluded.user_id,
            platform = excluded.platform,
            is_active = true,
            updated_at = now()
    returning * into result;
    return result;
end;
$$;

-- ===========================================================================
-- Enable Row Level Security so the policies in migrations/*.sql apply.
-- (The migration files ALTER/CREATE policies but assume RLS is already on.)
-- ===========================================================================
alter table public.zones            enable row level security;
alter table public.sensors          enable row level security;
alter table public.roads            enable row level security;
alter table public.villages         enable row level security;
alter table public.terrain_data     enable row level security;
alter table public.profiles         enable row level security;
alter table public.user_devices     enable row level security;
alter table public.sensor_readings  enable row level security;
alter table public.reports          enable row level security;
alter table public.report_media     enable row level security;
alter table public.risk_predictions enable row level security;
alter table public.alerts           enable row level security;
alter table public.notifications    enable row level security;
alter table public.recipients       enable row level security;
alter table public.model_feedback   enable row level security;
alter table public.response_tasks   enable row level security;
alter table public.satellite_data   enable row level security;
alter table public.incidents        enable row level security;
alter table public.incident_impacts enable row level security;
alter table public.relief_resources enable row level security;
alter table public.recovery_plans   enable row level security;
alter table public.recovery_steps   enable row level security;
alter table public.shelters         enable row level security;

-- Public read access for the map-facing reference layers (matches /api/public/*
-- endpoints, which serve zones/roads/villages/sensors without auth). Write access
-- is granted to AUTHORITY/ADMIN by the consolidated policies in the migrations.
create policy zones_public_select    on public.zones            for select using (true);
create policy roads_public_select    on public.roads            for select using (true);
create policy villages_public_select on public.villages         for select using (true);
create policy sensors_public_select  on public.sensors          for select using (true);
create policy predictions_public_select on public.risk_predictions for select using (true);
create policy alerts_public_select   on public.alerts           for select using (true);

-- Response & recovery data is operational (authority/field), not a public map
-- layer. The backend talks to Supabase with the service-role key, which bypasses
-- RLS; these policies additionally scope any *direct* authenticated access to
-- authorities. Idempotent via drop-if-exists so the block is safe to re-run.
drop policy if exists incidents_authority_all on public.incidents;
create policy incidents_authority_all on public.incidents
    for all using (public.is_authority()) with check (public.is_authority());
drop policy if exists incident_impacts_authority_all on public.incident_impacts;
create policy incident_impacts_authority_all on public.incident_impacts
    for all using (public.is_authority()) with check (public.is_authority());
drop policy if exists relief_resources_authority_all on public.relief_resources;
create policy relief_resources_authority_all on public.relief_resources
    for all using (public.is_authority()) with check (public.is_authority());
drop policy if exists recovery_plans_authority_all on public.recovery_plans;
create policy recovery_plans_authority_all on public.recovery_plans
    for all using (public.is_authority()) with check (public.is_authority());
drop policy if exists recovery_steps_authority_all on public.recovery_steps;
create policy recovery_steps_authority_all on public.recovery_steps
    for all using (public.is_authority()) with check (public.is_authority());

-- Shelters are a public safety layer: anyone — signed in or not — may read them,
-- because a person deciding where to run should never hit a login wall. Writes
-- (occupancy, status, new sites) stay with ADMIN/AUTHORITY.
drop policy if exists shelters_public_select on public.shelters;
create policy shelters_public_select on public.shelters for select using (true);
drop policy if exists shelters_authority_write on public.shelters;
create policy shelters_authority_write on public.shelters
    for all using (public.is_authority()) with check (public.is_authority());

commit;

-- =============================================================================
-- End of schema.sql
-- =============================================================================
