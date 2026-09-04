# NER-SLIDE — Response & Recovery Expansion (v3)

*What shipped, how to deploy it, and how to demo it.*
*Built from the 31 Aug 2026 idea list — see `ROADMAP_response_recovery.md` for the full assessment.*

## What this adds

The platform already did **predict → alert**. This release closes the loop with
**dispatch → live response → recovery**, plus an honest model-transparency view.
Four features, all wired end-to-end (DB → API → UI):

| Feature | What it does | Where |
|---|---|---|
| **A — Dispatch & routing** | Dispatch a team to a prioritized zone. The task auto-captures the nearest roads and flags any `BLOCKED`/`RESTRICTED` segments on the way. Tasks move `PENDING → DISPATCHED → EN_ROUTE → ON_SITE → RESOLVED`. | `/response` (Response page, extended) |
| **B — Live ops board** | One timestamped feed merging alerts, dispatches, incidents, field reports and road closures, plus live counters. Auto-refreshes every 20 s. | `/ops` (new) |
| **C — Model transparency panel** | Read-only "what the model predicts — and what it does *not*" view: features, operating threshold and why, training design, global importances, explicit "not designed for" list. | `/model` (new) |
| **D — Recovery module** | Confirmed **incidents**, per-village **impact/needs assessment**, and **relief-resource** tracking (shelter/food/water/medical/…), each with its own status lifecycle. | `/recovery` (new) |

Everything obeys the project's **no-fabricated-data** rule: every new record carries a
`source` tag, blank impact counts mean *"not assessed"* (never silently `0`), and route
access is **derived from stored road status** (`DERIVED_FROM_ROAD_STATUS`), never invented.

## Deploy (one migration + restart)

1. **Apply the schema.** Open the Supabase SQL editor and run `supabase/schema.sql`.
   It is **idempotent** — the new objects use `create table if not exists` /
   `add column if not exists`, so re-running is safe and won't touch existing data.
   New objects: `incidents`, `incident_impacts`, `relief_resources`, six new columns on
   `response_tasks` (`phase`, `team`, `route`, `incident_id`, `source`, `resolved_at`),
   their triggers, and RLS policies gated by `public.is_authority()`.
2. **Restart the backend.** No new environment variables are required. (Optional, unchanged:
   `OPERATIONAL_PREVALENCE` still enables prior-corrected risk; the Model Card shows whether
   it's on.)
3. **Rebuild the frontend** (`npm run build` / your usual step). The new routes and nav items
   appear automatically.

## New API surface

All under `/api`, all behind the existing auth. Role rules follow the current hierarchy
(`ADMIN ⊂ AUTHORITY ⊂ FIELD_OFFICER`).

```
# Feature C
GET   /model/transparency

# Feature A
POST  /response/dispatch            (AUTHORITY)   -> creates a DISPATCHED task with route
POST  /response/tasks               (FIELD_OFFICER)
GET   /response/tasks?phase=&status=&incident_id=
PATCH /response/tasks/{task_id}     (FIELD_OFFICER)

# Feature B
GET   /ops/activity?limit=
GET   /ops/summary

# Feature D
POST  /incidents                    (AUTHORITY)
GET   /incidents?status=
GET   /incidents/{incident_id}      (returns impacts + resources + linked tasks)
PATCH /incidents/{incident_id}      (AUTHORITY)
POST  /incidents/{incident_id}/impacts     (FIELD_OFFICER)
PATCH /impacts/{impact_id}                  (FIELD_OFFICER)
POST  /incidents/{incident_id}/resources   (AUTHORITY)
PATCH /resources/{resource_id}              (AUTHORITY)
```

`response_tasks` is reused for both phases via `phase` (`RESPONSE` | `RECOVERY`), so recovery
tasks linked to an incident show up inside that incident's detail view.

## Demo script (the loop, ~3 min)

1. **Live Ops (`/ops`)** — start here so judges see the system "breathing": counters + feed.
2. **Response (`/response`)** — the P1–P4 board ranks zones. Hit **Dispatch team** on a P1.
   A task appears on the dispatch board showing the **nearest roads** and, if any are down,
   a red **"Blocked on route"** line with an `IMPACTED` access chip. Advance it
   `DISPATCHED → EN_ROUTE → ON_SITE → RESOLVED`.
3. **Back to `/ops`** — the dispatch and status changes are now in the live feed.
4. **Recovery (`/recovery`)** — **Confirm incident** for the affected zone, file a
   **per-village impact** row (leave a count blank to show "not assessed" ≠ 0), and log a
   **relief resource** (e.g. SHELTER), advancing it `REQUESTED → ALLOCATED → IN_TRANSIT → DELIVERED`.
5. **Model Card (`/model`)** — pre-empt the "is it a black box?" question: threshold and why
   (recall ~0.98 @ 0.15), the matched-pair training caveat, and the explicit *not designed for*
   list.

## Not built yet (intentionally)

**Feature E — real government feeds (IMD / GSI / Bhuvan).** High credibility value, but it
depends on external API availability that must be verified live, so it's sequenced after a
demo that already works offline. The `source`-tag pattern is ready to receive it. See
`ROADMAP_response_recovery.md` §E.

## Verification done

- All backend Python byte-compiles (`compileall`, clean).
- All five new/edited frontend files parse under esbuild (JSX).
- All 14 frontend API paths resolve to a registered backend route.
- `schema.sql` new objects are ordered correctly (`is_authority()` defined before its
  policies) and are idempotent.

*Not runnable in this sandbox: `pytest` (needs scikit-learn) and executing `schema.sql`
(needs a live Postgres/PostGIS). Verification above is by construction.*
