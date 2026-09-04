# Supabase database — setup & provenance

This folder defines the NER-SLIDE database so a **fresh** Supabase project can be
rebuilt from the repo. Previously only the RLS/hardening migrations lived here;
the tables and PostGIS RPCs existed only in the live project. `schema.sql` closes
that gap.

## Do I need to run any of this?

- **Existing, working Supabase project** → you do **not** need to run `schema.sql`;
  your tables already exist. None of the recent code improvements (multilingual
  alerts, ML calibration) require a schema change — the alert provenance is stored
  inside the existing `translations` JSONB, and calibration fields are computed at
  request time and never persisted. Just keep your env vars set (below).
- **Brand-new / empty project (new demo env, teammate clone, DR)** → run the files
  in the order below.

## Run order (new project)

Run each in the Supabase SQL editor (or via `psql`):

1. `schema.sql` — extensions (pgcrypto, postgis), 17 tables, helper functions,
   triggers, the 8 RPCs the backend calls, RLS enabled + public-read policies.
2. `migrations/20260830_security_hardening.sql`
3. `migrations/20260830_rls_policy_consolidation_v3.sql`
4. `migrations/20260830_security_performance_hardening_v2.sql`
5. `migrations/20260830_response_tasks_policy_cleanup_v4.sql`
6. `migrations/20260831_grant_gis_access_to_backend_service_role.sql`
7. Seed the 22 NER demo zones (+ roads, villages, sensors):
   ```bash
   cd backend
   export SUPABASE_URL=... SUPABASE_SECRET_KEY=...
   python -m app.db.migration_seed
   ```

## Environment variables the backend expects

Set these on the backend service (see `backend/.env.example`):

- `SUPABASE_URL` — `https://<project-ref>.supabase.co`
- `SUPABASE_SECRET_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`) — server-only secret
- Frontend uses `SUPABASE_ANON_KEY` via `frontend/.env`

## Notes

- `schema.sql` is a faithful reconstruction from what the code reads/writes, not a
  `pg_dump` of the live DB. It is idempotent (`if not exists` / `or replace`) and
  safe to run on an empty project. **Diff it against production before running it
  against a database that already has data.**
- RPC return shapes were cross-checked against the mappers in
  `backend/app/db/supabase_repo.py`: `centroid` is returned as `{lat, lon}`,
  geometries as GeoJSON, and sensor/village points projected to `lat`/`lon`
  columns — so the Python layer works unchanged.
