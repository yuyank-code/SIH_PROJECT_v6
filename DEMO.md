# SIH Demo Script (≈5 minutes)

## 0. Sign in
- Open the site → `/login`
- Choose **Authority** → **Enter Ops Console**

## 1. Operations overview
- Point out the 8 stat cards: total zones, severity counts, sensors online, roads blocked, active alerts.
- The GIS map dominates the panel with risk polygons + heatmap circles, roads (blue OK, amber at-risk, red BLOCKED), sensors and villages.
- Legend is permanent bottom-left.
- Right rail shows Response Priorities and Recent Alerts.

## 2. Run risk over the whole NER
- Click **"Run risk over all zones"** — backend calls Open-Meteo historical rainfall for every seeded zone, merges it with each zone's terrain and runs the V5 model. Severity + priority are persisted.
- Map colours refresh; response priority list re-orders.

## 3. Pick a zone
- Click any orange/red polygon (or open **Zones** and pick "Cherrapunji Ridge").
- Show the zone detail:
  - Severity chip + risk score /100
  - Rainfall drivers (real Open-Meteo values for 1d/3d/7d/15d/30d + max_3d / max_7d / rainy_days_7d)
  - Terrain block (DEMO — flagged)
  - Nearby roads / villages / sensors
  - "Why is this zone at risk?" — LLM-written narrative built strictly from the numeric factors
  - Contributing factors ranked by V5 permutation importance

## 4. Simulate more rain
- Drag **Simulate rainfall** slider to 2.5×.
- Click **Apply** — the risk service re-runs the V5 model with scaled rainfall overrides.
- Severity typically flips to CRITICAL, risk score jumps.

## 5. Issue a multilingual alert
- Click **Issue multilingual alert** — creates an alert record; Emergent LLM key translates it into Assamese, Khasi, Mizo, Nepali, Bodo.
- Open **Alerts**; toggle language dropdown to see localized text.

## 6. Field officer reports a road block
- Open a new tab → `/field`.
- Tap **Get current location** → GPS captured; nearest road + status shown.
- Choose **ROAD_BLOCKAGE** → optional photo → **Submit report**.
- Backend marks the nearest road BLOCKED and flags the containing zone with `recent_field_report: true`.

## 7. Response priority updates
- Return to Authority dashboard.
- The affected zone climbs to **P1 — IMMEDIATE** because severity + road blockage + field report all stack.
- Click the P1 tile → jumps to zone detail; the "unknown factors" hint clearly lists what population/isolation data is *not* available so authorities know the priority calculation's limits.

## 8. Offline-first sync
- In DevTools → set Network → Offline. Submit another field report.
- The report is queued in localStorage. Turn Network → Online. Report auto-syncs; queue badge disappears.

## 9. Public / Citizen portal
- Visit `/public` — simplified public risk map, active alerts (with language switcher), and safety instructions.
- Note the two buttons above the alerts: **Where do I go?** and **Report what you can see**.
  A risk map that says CRITICAL and offers no next step leaves the reader worse off than before.

## 10. "Where do I go?" — the question a risk score provokes
- Click **Where do I go?** (or visit `/safety`). **Sign out first** to make the point: this
  page needs no login. Somebody standing on a moving slope must not meet a login wall.
- Allow location. The page returns, in priority order: move *sideways* out of the slope's
  path first (debris travels down the fall line faster than you can walk), then head to
  the named shelter.
- Open **Why this shelter?** on the recommendation — every scoring factor is listed.
- Scroll to **What this is based on**: distances are straight-line, walking assumes
  4 km/h, and a road absent from the hazard list is *unsurveyed, not known to be safe*.
  There is no routing engine and the page says so.
- Judge-proofing: set a coordinate far from any shelter (e.g. 27.0, 95.5). The page flags
  **transport required** and leads with "do not set out on foot" instead of quoting a
  multi-hour walking time. An earlier build recommended a 267 km shelter with a tidy
  "4001 min" beside it; that bug is now a pinned regression test.

## 11. Citizen reporting with a photo
- Visit `/report` while signed in as any profile, including CITIZEN.
- GPS is captured, not typed, and shown with its accuracy so a poor lock is visible.
- Pick a type, attach a photo, submit.
- Go to `/reports` as a field officer: the claim appears with a photo thumbnail and a
  **corroboration** chip. File a second report from a *different* account at the same
  spot and it becomes **CORROBORATED** — the count is by distinct reporter, so one
  person refreshing cannot manufacture agreement.
- Triage it. Rejections are stamped with who and when, just like confirmations, and a
  rejected report stops voting in the corroboration count.

## 12. Shelter occupancy (`/shelters`)
- Two seeded shelters show **"Capacity not recorded"** and one is CLOSED. That is on
  purpose — a real register is always partly incomplete.
- Leaving the occupancy box empty means *no change*. To record an actually-empty
  shelter you type `0`. A blank is never read as zero anywhere in the stack.

## What's real vs DEMO
- **Real:** Open-Meteo forecast + historical rainfall; Open-Meteo elevation; OSM tiles; V5 model predictions.
- **DEMO (labelled):** terrain features per zone, sensors, road segments, villages, shelters (`SEED_DEMO`).
- Satellite/IMD/FCM/SMS integrations are stubs with explicit *unavailable* status until credentials are provided.
- Shelter distances are straight-line, not routed. No turn-by-turn navigation is claimed.
