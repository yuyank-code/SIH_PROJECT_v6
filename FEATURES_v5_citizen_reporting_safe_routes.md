# v5 — Citizen reporting with photos, and safe-route / shelter recommendation

Two additions, both aimed at the same gap: the platform could tell you a slope was
about to fail, and then left you holding that information with nothing to do about it.

1. **Citizen reporting with photo upload** — ground truth flows *into* the system
   from the people standing in front of the hazard, not just from sensors and the model.
2. **Safe route + shelter recommendation** — the system now answers the question a
   risk score provokes: *so where do I go?*

Everything below is additive. No existing route changed shape, the V5 model files are
byte-identical to the previous build, and the v4 recovery/monitoring suite still passes.

---

## 1. Citizen reporting with photo upload

### The gap

Reporting infrastructure already existed, but it was unreachable by the people it was
for. `POST /api/reports` and the private `report-media` storage bucket were in place,
yet the only UI that used them was `/field`, which is gated to `FIELD_OFFICER` and
above. A citizen who opened `/public`, saw a CRITICAL zone and wanted to say *"the
road below my house just cracked"* had nowhere to do it. The one hint the old UI gave
was a dead-end line of text reading "Sign in before submitting a report."

### What was built

**`/report` — a citizen reporting page** (`frontend/src/pages/Report.jsx`, new)

A four-step form: location, what you see, a photo, a description. Design decisions
worth naming:

- **GPS is captured, not typed.** A person in distress should not be converting their
  position into decimal degrees. Accuracy is shown alongside the fix so a poor lock is
  visible rather than silently trusted.
- **The photo is optional.** A report with no photo is still worth having; a report
  that fails to send because someone was on 2G in a valley is not. The camera capture
  is read to a data URL, which is what lets an unsent report carry its photo into the
  offline queue. (Known limitation: it is *not* downscaled before upload, so a modern
  phone photo goes up at full size. Client-side compression is the obvious next
  improvement for low-bandwidth districts.)
- **Offline-first.** If the network is down the report is queued locally and flushed
  when connectivity returns. The confirmation screen distinguishes *sent* from
  *queued* — telling someone their report reached responders when it is sitting in
  local storage would be the worst possible lie for this screen to tell.
- **Seven report types** matching the field-officer vocabulary, so citizen and officer
  reports are directly comparable rather than living in separate taxonomies.

**It requires sign-in, deliberately.** Anonymous reporting looks more accessible but
would make the corroboration signal (below) forgeable by one person with a refresh
button — which is worse than having no signal at all. The route admits *any* signed-in
profile including `CITIZEN`, and renders its own sign-in prompt rather than bouncing
to a login wall.

**Corroboration** (`backend/app/services/citizen_service.py`)

The most useful thing a triaging officer can know about a claim is whether anyone
*else*, independently, is saying the same thing. Each report is scored:

| Signal | Meaning |
| --- | --- |
| `CONFIRMED` | a human has verified at least one report here |
| `CORROBORATED` | two or more **distinct** reporters, independently |
| `SINGLE` | one reporter |
| `NONE` | nothing in the window and radius |

Counting is by **distinct reporter identity**, not report volume — one person filing
three reports is one witness, and the test suite pins that. `REJECTED` and `DUPLICATE`
reports never vote, so a dismissed claim cannot quietly re-enter the count. Anonymous
reports collapse to a single collective voice for the same reason.

**A triage queue** (`frontend/src/pages/Reports.jsx`, rewritten)

Status tabs, a backlog summary, photo thumbnails via short-lived signed URLs, and a
per-report triage panel. Rejections are stamped with who and when, exactly like
confirmations: "someone checked and said no" is a finding worth keeping.

### Two pre-existing bugs fixed at the source

- **`nearest_zone_id` was never persisted.** Reports were computed against a nearest
  zone and the link was then thrown away, so no report could ever be correlated to the
  zone it concerned. Now stored, using the same haversine as the routing engine.
- **`Reports.jsx` read fields that did not exist** — `r.timestamp` (the column is
  `created_at`) and `r.zone_id` (the enriched payload provides `zone_name`). The page
  had been rendering "Invalid Date" and blank zones.

---

## 2. Safe route + shelter recommendation

### What it does

`/safety` — reachable **without signing in** — takes the visitor's GPS position and
returns ranked shelters, ordered movement guidance, and nearby road hazards.

A person deciding where to run must never meet a login wall, so the read paths are
mirrored under `/api/public/` which the auth middleware exempts by prefix.

### Honesty about what this is not

There is no routing engine here, and the payload says so. Every recommendation ships
an `assumptions` block stating that distances are **straight-line**, that walking
times assume 4 km/h on the flat, and — the important one — that a road absent from the
hazard list is *unsurveyed, not known to be safe*. Inventing a turn-by-turn route
across landslide terrain from data the system does not have would be the single most
dangerous thing this feature could do.

Shelter `capacity` and `current_occupancy` are nullable end to end — seed, migration,
API, both UIs. A missing count renders as "not recorded" or "occupancy not counted
yet", never as `0`. In the operations panel an empty occupancy box means *no change*;
to record an actually-empty shelter an operator types `0` explicitly.

### Ranking

Shelters are scored on distance, operational status, headroom, elevation above the
valley floor, and proximity to a live risk zone — each contribution listed in a
`reasons` array so an operator can see why something ranked where it did.

Guidance is ordered by priority and leads with lateral movement: **debris travels down
the fall line faster than you can walk**, so moving sideways out of the slope's path
comes before heading anywhere else.

### A serious bug found and fixed during verification

The first end-to-end run of the finished engine, from Sohra, recommended:

```
#1  Ukhrul Government School   266.71 km   score=65   walk ~4001 min
    Sohra Community Hall         1.07 km   ranked below
```

A 66-hour walk, presented as the top recommendation, with a tidy four-digit
walking time beside it.

**Root cause.** The distance penalty was `min(40.0, distance_km * 4.0)`. It saturates
at 10 km — so every shelter beyond 10 km scored *identically* on distance, and the
267 km one then won the tiebreak by not happening to sit near a CRITICAL zone. The cap
looked like sensible defensive clamping and was in fact the bug.

**The fix, in five parts:**

1. A non-saturating two-segment penalty, so distance keeps discriminating all the way
   out. Two shelters 40 km and 300 km away no longer tie.
2. `WALKABLE_RADIUS_KM = 15.0` — an explicit, published horizon for what "go there"
   can mean on foot.
3. `walk_estimate_minutes` returns `None` past that horizon instead of a number.
   "4001 min" answers the arithmetic while implying the journey is something a person
   could set off and do. Silence is more honest.
4. `requires_transport` promoted to a **sort key**, not merely a score input. A
   weighted sum can always be gamed by an unlucky combination of factors; making "can
   this person actually walk there?" its own ordering term guarantees a reachable
   nearby shelter outranks a distant one regardless of how the penalties land.
5. When nothing is walkable the payload sets `transport_only` and the guidance leads
   with *"Do not set out on foot"* — the best option is still named, because
   withholding it helps nobody, but reaching it needs a vehicle and the page says so.

This is now a pinned regression test. `v5_logic_checks.py` asserts that a ~267 km
shelter never outranks a ~1 km one, and that no walking time is ever produced past
the walkable radius.

---

## Files

**New backend**

| File | Purpose |
| --- | --- |
| `app/services/safe_route_service.py` | geometry, shelter scoring, hazards, movement guidance |
| `app/services/citizen_service.py` | corroboration signal, triage transitions, triage summary |

**New frontend**

| File | Purpose |
| --- | --- |
| `pages/Safety.jsx` | citizen "where do I go?" page, no sign-in |
| `pages/Report.jsx` | citizen reporting with GPS, photo, offline queue |
| `pages/Shelters.jsx` | operations shelter/occupancy management |

**Modified** — `server.py` (8 new shelter/safe-route routes; 7 report routes reworked),
`app/db/supabase_repo.py`,
`app/data/ner_seed.py` (13 demo shelters), `app/db/migration_seed.py`,
`supabase/schema.sql` (shelters table, triage columns, two RPCs, RLS),
`pages/Reports.jsx` (rewritten), `pages/Public.jsx`, `components/RiskMap.jsx`,
`components/Shell.jsx`, `App.js`, and `API.md` (see below).

**Unchanged, verified byte-identical** — `app/services/ml_service.py`,
`scripts/run_risk_predictions.py`, `tests/test_ml_regression.py`,
`ml/v5_final_model.joblib`.

## Endpoints

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `/api/public/safe-route?lat=&lon=&limit=` | public |
| `GET` | `/api/public/shelters` | public |
| `GET` | `/api/public/gis/shelters` | public |
| `GET` | `/api/safe-route` · `/api/shelters` · `/api/gis/shelters` | signed-in |
| `POST` | `/api/reports` · `/api/reports/{id}/media` | signed-in (CITIZEN included) |
| `GET` | `/api/reports` · `/reports/summary` · `/reports/corroboration` · `/reports/{id}/media` | signed-in |
| `PATCH` | `/api/reports/{id}` (triage) | FIELD_OFFICER |
| `PATCH` | `/api/shelters/{id}` (occupancy, status) | FIELD_OFFICER |
| `POST` | `/api/shelters` | AUTHORITY |

Occupancy updates sit with `FIELD_OFFICER` on purpose: the officer at the gate
counting people in is the one who knows, and a stale occupancy figure is precisely
what sends the next family to a full camp.

## Database

`supabase/schema.sql` gains, all idempotent:

- `public.shelters` — GiST index on `location`, nullable `capacity` /
  `current_occupancy`, `source`, `updated_at` trigger
- `public.reports` — `nearest_zone_id`, `verified_by`, `verified_at`,
  `verification_note`, added via `add column if not exists`
- `public.nearby_shelters(lat, lon, limit)` and `public.list_shelters_geojson()`
- RLS: shelters are world-readable, writable only by `AUTHORITY`/`ADMIN`

13 demo shelters seed with `source: "SEED_DEMO"`. Two carry no capacity figure and
one is `CLOSED` on purpose — a real register is always partly incomplete, and the
platform must render that rather than paper over it.

## API.md regenerated from source

`API.md` had drifted badly: it documented 27 of 81 registered routes, none of them
newer than v3. It is now **generated from the live FastAPI route table** by
`gen_api_md.py`, reading each route's real path, access level (resolved through both
the auth middleware and its `require_roles` gate) and docstring. It cannot claim an
endpoint that does not exist or miss one that does. Re-run after adding routes.

## Verification

`cd verification && ./verify_v5.sh` — all green:

| Step | Result |
| --- | --- |
| backend compiles | clean |
| v4 recovery/monitoring suite | passing (no regression) |
| v5 logic checks | **107 checks, 0 failed** |
| v5 route table (real `server.py` imported against stubs) | clean |
| v5 static checks (icons, dead imports, API path map, secrets) | clean |
| JSX balance, 10 changed/new files | clean |
| ML surface vs baseline | byte-identical |

The route-table check imports the **actual** `server.py` against stub libraries, so it
catches what grep cannot: duplicate registrations, a handler calling a repo function
that does not exist, literal paths shadowed by parameterised siblings, and whether
each route's protection matches its documented intent.

Real defects caught by these harnesses and fixed: a dead `severityClass` import in
`Reports.jsx`; a `shelters` layer that `Public.jsx` would have silently hidden by
passing an explicit `layers` object that overrode the new default; and four
pre-existing unused imports the CRA build was warning about (`SEVERITY_COLORS`,
`HardDrives`, `Path` in `Dashboard.jsx`, `uploadReportMedia` in `FieldOfficer.jsx`
— which imports the raw-`File` upload path it never calls, rather than the
data-URL one it actually uses).

The harness itself ships in `verification/` and runs from inside the package. The
two steps that compare against the pre-v5 baseline — the ML byte-identity check
and the phosphor icon attestation — **skip loudly** when no baseline is present,
because a check that goes green after its input disappears is worse than one that
admits it did not run. `verification/README.md` explains the design.

No npm or PyPI access is available in this environment, so verification is by
construction. What that does **not** cover: a real browser render, live Supabase
queries, and actual model scoring.
