# NER-SLIDE — Recovery Playbook & Monitoring Upgrade (v4)

*What shipped, how to deploy it, and how to demo it.*
*Builds on v3 (`FEATURES_response_recovery.md`). The monitoring/prediction loop and the
Recovery module already existed — v4 deepens both rather than replacing them.*

## What this adds

v3 gave the platform **predict → alert → dispatch → respond → record the incident**.
Two gaps were left open: the monitoring screen showed *severity* but not *what to do about
it*, and the Recovery module could record impacts and relief resources but could not answer
the operator's actual question — **"how do we recover, and what are the steps?"**

v4 closes both. Four additions, all wired end-to-end (DB → API → UI):

| Feature | What it does | Where |
|---|---|---|
| **F — Recovery Playbook** | A phased, 31-step recovery checklist generated per confirmed incident from an NDMA/Sphere-aligned template: *relief → early recovery → restoration → rehabilitation & resilience*. Each step carries an owner, status, a **"manageable when"** gate and an **on-ground-check** flag. Progress is tracked per phase. | `/recovery` (extended) |
| **G — Monitoring Watchboard** | Turns stored predictions into an operational watch picture: **watch level** (WARNING/WATCH/ADVISORY/STAND-DOWN) instead of a bare severity band, a **rainfall trend** (rising/steady/falling), and a **freshness** flag so a watch picture that has gone cold is itself visible. | `/ops` (extended) |
| **H — SITREP generator** | One-click situation report for an incident, composed from records already on the platform and copyable as Markdown for a WhatsApp/email handoff. | `/recovery` (extended) |
| **I — Recovery Overview** | Cross-incident status table: where each incident's recovery stands, which phase it is in, and how many steps are blocked waiting on a field visit. | `/recovery` (extended) |

Everything obeys the project's **no-fabricated-data** rule. The trend is derived from the
prediction's own stored features and tagged `DERIVED_FROM_PREDICTION_FEATURES`; when the
features are missing the trend is `UNKNOWN` with source `UNAVAILABLE`, never a guessed
number. An incident with no recovery plan reports `plan: null`, never a fabricated `0%`.
SITREP totals sum only assessed villages and state how many are still *not assessed*.

## The recovery checklist — what "recover" actually means here

The template is 31 steps across four phases, gated by severity so a minor cut-slope failure
does not inherit a mass-casualty checklist:

| Phase | Window | Steps |
|---|---|---|
| Immediate relief | 0–72 hours | 10 |
| Early recovery | First weeks | 7 |
| Restoration | Weeks to months | 6 |
| Rehabilitation & resilience | Months onward | 8 |

A `LOW`/`MEDIUM` incident gets 29 steps, `HIGH` gets 30 (adds *Request NDRF/SDRF
deployment*), `CRITICAL` gets all 31 (adds *Stand up mass-casualty triage and mortuary
arrangements*). Steps run from *Launch search & rescue at the slide site* and *Cut power and
fuel lines across the run-out zone* through *Reopen the road with a monitored single lane*
and *Install slope drainage and a toe wall* to *Re-survey the slope and update the hazard
zone*.

Two fields make the checklist honest rather than decorative:

- **`manageable_when`** — the condition that must hold before a step is realistically
  actionable ("As soon as the site is reachable", "Once the debris flow has stopped").
  It stops a plan from reading as a flat to-do list when the phases genuinely gate each other.
- **`requires_assessment`** — 27 of the 31 steps cannot be honestly marked *done* from a
  desk; they need a survey, a site visit or a verified count. The UI labels these
  **"needs on-ground check"**, and the overview counts open ones per incident, so a plan
  cannot quietly reach 100% on paper while nobody has been to the slope.

Status is `PENDING | IN_PROGRESS | DONE | NA`. **`NA` is excluded from the denominator**, so
marking a step not-applicable neither inflates nor deflates progress — a phase of only-`NA`
steps reads `0/0`, not a false 100%.

Plan generation is **idempotent and progress-preserving**. Re-running it never duplicates a
step and never resets one. If an incident is later upgraded (say `HIGH → CRITICAL`), pressing
**Sync steps** tops up only the steps that severity unlocks, leaving completed work intact.
There is deliberately no destructive reset path: wiping a worked checklist would destroy real
field progress.

## The monitoring upgrade — from severity to a watch picture

`monitoring_service.py` reshapes predictions the platform already stores. No new network
calls, no new model, no change to the V5 feature set.

- **Watch level.** Severity maps to an operational level plus a plain-language cue —
  `CRITICAL → WARNING, "Act now — evacuate and dispatch"`, `MEDIUM → WATCH, "Watch closely —
  conditions are building"`, and so on.
- **Rainfall trend.** `rainfall_3d` is rain in the last three days; `rainfall_7d` is the last
  seven, so the earlier part of the week is `7d − 3d`. If the recent three days already carry
  materially more rain than the earlier four, the slope is being loaded fast → **RISING**.
- **Escalation with a stated reason.** A `MEDIUM` zone on a **RISING** trend escalates from
  WATCH to WARNING, because worsening rain on a watched slope is exactly when to lean
  forward. The escalation is never silent: every row ships a `rationale` array
  (`["severity=MEDIUM", "rainfall_trend=RISING"]`) and an `escalated` flag.
- **Staleness.** A prediction older than `STALE_AFTER_HOURS` (6h) is flagged. The summary
  publishes the threshold so the number on screen is auditable rather than magic.

## Deploy (one migration + restart)

1. **Apply the schema.** Open the Supabase SQL editor and run `supabase/schema.sql`. It stays
   **idempotent** (`create table if not exists`, `add column if not exists`,
   `drop policy if exists`), so re-running is safe and will not touch existing data. New in
   v4: tables `recovery_plans` (one per incident, unique on `incident_id`) and
   `recovery_steps` (unique on `(plan_id, code)`), their `updated_at` triggers, RLS policies
   gated by `public.is_authority()`, and the two guidance columns
   `requires_assessment boolean not null default false` and `manageable_when text default ''`
   — added via `alter table ... add column if not exists` so installs created before v4
   upgrade cleanly.
2. **Restart the backend.** No new environment variables. Server-only secrets
   (`SUPABASE_SECRET_KEY` / `SUPABASE_SERVICE_ROLE_KEY` / `FIREBASE_SERVICE_ACCOUNT_JSON`)
   remain server-side and are not exposed to the frontend.
3. **Rebuild the frontend.** The new panels appear on the existing `/recovery` and `/ops`
   routes — no new nav entries to wire up.

## New API surface

All under `/api`, behind the existing auth, following the current role hierarchy
(`ADMIN ⊂ AUTHORITY ⊂ FIELD_OFFICER`).

| Method | Path | Role | Notes |
|---|---|---|---|
| `GET` | `/recovery/playbook` | read | The template itself (phases + full step list) so the UI can preview what a plan will contain. Guidance content, not event data. |
| `GET` | `/recovery/overview?limit=100` | read | One row per incident: phase, progress, `awaiting_assessment`. Bulk-fetched (no N+1). Incidents without a plan return `plan: null`. |
| `POST` | `/incidents/{id}/recovery-plan` | AUTHORITY | Generate or top up. Idempotent; never duplicates, never resets. |
| `GET` | `/incidents/{id}/recovery-plan` | read | Plan + steps + per-phase progress. `404 no_recovery_plan` if none. |
| `POST` | `/recovery-plans/{plan_id}/steps` | FIELD_OFFICER | Add a manual step (`source=MANUAL`, auto `MANUAL-` code); accepts `requires_assessment`. |
| `PATCH` | `/recovery-steps/{step_id}` | FIELD_OFFICER | Status/owner/notes/due date. Stamps `done_at` on `DONE` and clears it on revert. |
| `GET` | `/incidents/{id}/sitrep` | read | `{markdown, totals, generated_at}` composed from stored records. |
| `GET` | `/monitoring/watchboard` | read | One row per predicted zone: watch level, cue, rationale, trend, freshness. Sorted most-urgent-first. |
| `GET` | `/monitoring/summary` | read | Counts by level, stale-zone count, published staleness threshold. |
| `GET` | `/public/monitoring/watchboard` | public | Same watch picture for the public-facing view. |

The overview reuses the **same** server-side progress function as the detail page, so the
numbers in the table provably match the numbers on the plan — they cannot drift.

## Demo path (about two minutes)

1. Open **`/ops`**. The first tile reads *Zones on warning*. Point at a `MEDIUM` zone that has
   escalated to **WARNING** and read its rationale aloud — the board explains its own
   decision. Point at a stale row: *"this zone's picture has gone cold, that is itself a
   risk."*
2. Open **`/recovery`**. The overview table shows every incident, the phase it is in, its
   progress, and how many steps are waiting on a field check.
3. Pick an incident → **Generate plan**. The 31-step phased checklist appears. Work a couple
   of steps; mark one `NA` and show that progress stays honest.
4. Show a step's *when:* gate and its *needs on-ground check* chip — *"we cannot tick this
   from a desk."*
5. Hit **SITREP**, copy the Markdown, and note the *"(n village(s) not yet assessed)"* line:
   the report says what it does not know.

## Verification

No package installs or network access were available while building this, so everything was
verified by construction:

- **`backend/` compiles clean** (`python3 -m compileall` across `server.py` and all of `app/`).
- **60+ logic checks pass** against a fake-Supabase harness that executes the real repository
  query-builder code paths — covering severity gating, phase ordering, `NA` progress
  arithmetic, current-phase selection, plan idempotency and severity top-up, overview
  aggregation, and every monitoring branch (rising/steady/falling/unknown trend, escalation,
  staleness, empty input).
- **JSX structure validated** on both edited pages; no unused imports introduced (diffed
  against the untouched v3 baseline so pre-existing issues are not misattributed).
- **Every frontend `api.*` call maps to a defined route** — 57 calls against 69 routes, zero
  unresolved.
- **The ML surface is byte-identical to v3.** `ml_service.py`, `risk_service.py`, `model/` and
  `backend/tests/` are unchanged, so the V5 feature order and the ML regression tests are
  untouched by construction. (They could not be *run* here — `scikit-learn` is not installable
  in this sandbox — so run `pytest backend/tests/test_ml_regression.py` once locally to
  confirm.)

Two real bugs were found and fixed during that pass: **Sync steps** was a no-op after a
severity upgrade (an early return skipped the top-up), and the schema was missing the two
guidance columns the API had begun writing.
