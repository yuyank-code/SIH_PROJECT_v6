# API reference

All 81 endpoints registered by `backend/server.py`, generated from the route
table itself (`python3 gen_api_md.py`) so it cannot drift from the code.


## Authentication

Every path under `/api/` requires a `Authorization: Bearer <supabase-jwt>` header
**except** the paths listed under *Public* below, which the auth middleware exempts
by prefix (`/api/public/`) or by name (`/api/health`, `/api/model/info`, `/docs`,
`/openapi.json`, `/redoc`).

The **Access** column means:

| Value | Meaning |
| --- | --- |
| `public` | no token required |
| `signed-in` | any authenticated profile, including `CITIZEN` |
| `FIELD_OFFICER` | `FIELD_OFFICER`, `AUTHORITY` or `ADMIN` |
| `AUTHORITY` | `AUTHORITY` or `ADMIN` |

Roles nest: `ADMIN ⊂ AUTHORITY ⊂ FIELD_OFFICER ⊂ signed-in`. A citizen reaching a
role-gated route gets `403`; an unauthenticated request to a non-public route gets `401`.


## Health & model

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/health` | public | _(no description in source)_ |
| `GET` | `/api/me` | signed-in | _(no description in source)_ |
| `POST` | `/api/model/feedback` | AUTHORITY | `FeedbackReq` body. |
| `GET` | `/api/model/info` | public | _(no description in source)_ |
| `GET` | `/api/model/transparency` | signed-in | What the model predicts, its operating point, and what it is NOT for. All numbers come from the shipped model artifacts — nothing is fabricated. |

## Zones & GIS

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/gis/alerts` | signed-in | _(no description in source)_ |
| `GET` | `/api/gis/heatmap` | signed-in | _(no description in source)_ |
| `GET` | `/api/gis/nearby` | signed-in | _(no description in source)_ |
| `GET` | `/api/gis/reports` | signed-in | _(no description in source)_ |
| `GET` | `/api/gis/risk-zones` | signed-in | _(no description in source)_ |
| `GET` | `/api/gis/roads` | signed-in | _(no description in source)_ |
| `GET` | `/api/gis/sensors` | signed-in | _(no description in source)_ |
| `GET` | `/api/gis/shelters` | signed-in | Shelters as GeoJSON for the operations map. |
| `GET` | `/api/gis/villages` | signed-in | _(no description in source)_ |
| `GET` | `/api/terrain/elevation` | signed-in | _(no description in source)_ |
| `POST` | `/api/terrain/recompute` | AUTHORITY | _(no description in source)_ |
| `GET` | `/api/weather` | signed-in | _(no description in source)_ |
| `GET` | `/api/weather/history` | signed-in | _(no description in source)_ |
| `GET` | `/api/zones` | signed-in | _(no description in source)_ |
| `GET` | `/api/zones/{zone_id}` | signed-in | _(no description in source)_ |

## Sensors

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/sensors` | signed-in | _(no description in source)_ |
| `POST` | `/api/sensors/readings` | FIELD_OFFICER | `SensorReading` body. |

## Citizen reporting

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/reports` | signed-in | Reports with media counts, resolved zone names, and corroboration. |
| `POST` | `/api/reports` | signed-in | `ReportCreate` body. Accept a report from anyone signed in — including a CITIZEN. |
| `GET` | `/api/reports/corroboration` | signed-in | Zones where citizens are independently reporting the same thing. |
| `GET` | `/api/reports/summary` | signed-in | Triage backlog at a glance — how many claims are still unlooked-at. |
| `PATCH` | `/api/reports/{report_id}` | FIELD_OFFICER | `ReportTriage` body. Record a human's verdict on a claim: verified, rejected, duplicate, actioned. |
| `GET` | `/api/reports/{report_id}/media` | signed-in | Signed, short-lived URLs for a report's photo evidence. |
| `POST` | `/api/reports/{report_id}/media` | signed-in | Attach an uploaded photo to a report the caller is allowed to touch. |

## Shelters & safe routes

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/safe-route` | signed-in | Ranked shelters plus ordered movement guidance for a point. |
| `GET` | `/api/shelters` | signed-in | Every shelter with its status and recorded occupancy. |
| `POST` | `/api/shelters` | AUTHORITY | `ShelterUpsert` body. Register or replace a shelter record. |
| `PATCH` | `/api/shelters/{shelter_id}` | FIELD_OFFICER | `ShelterUpdate` body. Update occupancy or status. Field officers can do this — they are the ones standing at the gate counting people in, and a stale occupancy figure… |

## Alerts & notifications

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/alerts` | signed-in | _(no description in source)_ |
| `POST` | `/api/alerts` | AUTHORITY | `AlertCreate` body. |
| `GET` | `/api/notifications` | signed-in | _(no description in source)_ |
| `GET` | `/api/notifications/status` | signed-in | _(no description in source)_ |
| `GET` | `/api/recipients` | AUTHORITY | _(no description in source)_ |
| `POST` | `/api/recipients` | AUTHORITY | `RecipientCreate` body. |
| `DELETE` | `/api/recipients/{recipient_id}` | AUTHORITY | _(no description in source)_ |

## Response & dispatch

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/response/dispatch` | AUTHORITY | `DispatchRequest` body. Create a DISPATCHED response task for a zone, attaching the nearest route and flagging any blocked segments on the way, plus the current P1-P4… |
| `GET` | `/api/response/priorities` | AUTHORITY | _(no description in source)_ |
| `GET` | `/api/response/tasks` | signed-in | _(no description in source)_ |
| `POST` | `/api/response/tasks` | FIELD_OFFICER | `TaskCreate` body. |
| `PATCH` | `/api/response/tasks/{task_id}` | FIELD_OFFICER | `TaskUpdate` body. |

## Recovery

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `PATCH` | `/api/impacts/{impact_id}` | FIELD_OFFICER | `ImpactUpdate` body. |
| `GET` | `/api/incidents` | signed-in | _(no description in source)_ |
| `POST` | `/api/incidents` | AUTHORITY | `IncidentCreate` body. |
| `GET` | `/api/incidents/{incident_id}` | signed-in | _(no description in source)_ |
| `PATCH` | `/api/incidents/{incident_id}` | AUTHORITY | `IncidentUpdate` body. |
| `POST` | `/api/incidents/{incident_id}/impacts` | FIELD_OFFICER | `ImpactCreate` body. |
| `GET` | `/api/incidents/{incident_id}/recovery-plan` | signed-in | _(no description in source)_ |
| `POST` | `/api/incidents/{incident_id}/recovery-plan` | AUTHORITY | Generate (or top up) the recovery plan for an incident. Idempotent: never duplicates a step already present, never resets progress. |
| `POST` | `/api/incidents/{incident_id}/resources` | AUTHORITY | `ResourceCreate` body. |
| `GET` | `/api/incidents/{incident_id}/sitrep` | signed-in | _(no description in source)_ |
| `POST` | `/api/recovery-plans/{plan_id}/steps` | FIELD_OFFICER | `RecoveryStepCreate` body. |
| `PATCH` | `/api/recovery-steps/{step_id}` | FIELD_OFFICER | `RecoveryStepUpdate` body. |
| `GET` | `/api/recovery/overview` | signed-in | Cross-incident recovery status: one row per incident with its phase, progress and how many steps are waiting on an on-ground assessment. Incidents… |
| `GET` | `/api/recovery/playbook` | signed-in | The template itself (phases + full step list) so the UI can preview what a plan will contain. Pure guidance content — not event data. |
| `PATCH` | `/api/resources/{resource_id}` | AUTHORITY | `ResourceUpdate` body. |

## Monitoring & live ops

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/monitoring/summary` | signed-in | _(no description in source)_ |
| `GET` | `/api/monitoring/watchboard` | signed-in | _(no description in source)_ |
| `GET` | `/api/ops/activity` | signed-in | _(no description in source)_ |
| `GET` | `/api/ops/summary` | signed-in | _(no description in source)_ |

## Predictions (V5 model)

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/predictions/predict` | signed-in | `PredictRequest` body. |
| `POST` | `/api/predictions/run-all` | AUTHORITY | _(no description in source)_ |
| `POST` | `/api/predictions/zone` | AUTHORITY | `ZonePredictRequest` body. |
| `GET` | `/api/predictions/{zone_id}` | signed-in | _(no description in source)_ |

## Dashboard & analytics

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/dashboard/summary` | signed-in | _(no description in source)_ |

## Explainability & satellite

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/explain` | signed-in | `ExplainRequest` body. |
| `GET` | `/api/satellite/search` | signed-in | _(no description in source)_ |

## Public (no sign-in required)

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/public/alerts` | public | _(no description in source)_ |
| `GET` | `/api/public/gis/heatmap` | public | _(no description in source)_ |
| `GET` | `/api/public/gis/risk-zones` | public | _(no description in source)_ |
| `GET` | `/api/public/gis/roads` | public | _(no description in source)_ |
| `GET` | `/api/public/gis/shelters` | public | Shelters as GeoJSON for the citizen map — no sign-in. |
| `GET` | `/api/public/gis/villages` | public | _(no description in source)_ |
| `GET` | `/api/public/monitoring/watchboard` | public | _(no description in source)_ |
| `GET` | `/api/public/safe-route` | public | The "where do I go?" answer, reachable without a login. |
| `GET` | `/api/public/shelters` | public | Shelter directory for citizens — no sign-in. |
| `GET` | `/api/public/zones` | public | _(no description in source)_ |

## Request bodies

Field names below are the pydantic models in `backend/server.py`. A `?` marks an
optional field. Optional numeric fields default to `null`, never `0` — a missing
count means *not recorded*, and the UI renders it as such rather than implying a
value of zero.

- **`AlertCreate`** — `zone_id`, `severity`, `reason`, `recommended_action?`
- **`ExplainRequest`** — `severity`, `factors`, `zone_name`
- **`ImpactUpdate`** — `affected_population?`, `households?`, `casualties?`, `injured?`, `status?`, `needs?`, `notes?`
- **`IncidentCreate`** — `zone_id?`, `title`, `severity?`, `summary?`, `occurred_at?`
- **`IncidentUpdate`** — `status?`, `severity?`, `summary?`, `title?`
- **`ImpactCreate`** — `village_id?`, `village_name?`, `affected_population?`, `households?`, `casualties?`, `injured?`, `status?`, `needs?`, `notes?`
- **`ResourceCreate`** — `resource_type`, `label?`, `quantity?`, `unit?`, `status?`, `notes?`
- **`FeedbackReq`** — `zone_id`, `prediction_id?`, `label`, `notes?`
- **`PredictRequest`** — `features`
- **`ZonePredictRequest`** — `zone_id`, `rainfall_override?`
- **`RecipientCreate`** — `name`, `phone`, `role?`, `district?`, `language?`
- **`RecoveryStepCreate`** — `phase?`, `title`, `detail?`, `owner?`, `requires_assessment?`
- **`RecoveryStepUpdate`** — `status?`, `owner?`, `notes?`, `due_at?`, `title?`, `detail?`
- **`ReportCreate`** — `lat`, `lon`, `report_type`, `description?`, `reporter_role?`, `reporter_name?`, `client_uuid?`
- **`ReportTriage`** — `status`, `note?`, `incident_id?`
- **`ResourceUpdate`** — `status?`, `quantity?`, `unit?`, `label?`, `notes?`
- **`DispatchRequest`** — `zone_id`, `title?`, `team?`, `description?`
- **`TaskCreate`** — `zone_id?`, `title`, `description?`, `team?`, `priority?`, `phase?`, `status?`, `incident_id?`
- **`TaskUpdate`** — `status?`, `team?`, `priority?`, `title?`, `description?`
- **`SensorReading`** — `sensor_id`, `measurement_type`, `value`
- **`ShelterUpsert`** — `shelter_id`, `name`, `lat`, `lon`, `category?`, `status?`, `capacity?`, `current_occupancy?`, `elevation_m?`, `contact_phone?`, `managed_by?`, `district?`, `state?`, `source?`
- **`ShelterUpdate`** — `status?`, `capacity?`, `current_occupancy?`, `contact_phone?`, `managed_by?`

## Conventions

- Every record and computed payload carries a `source` field naming its provenance
  (`SEED_DEMO`, `AUTHORITY`, `SENSOR`, `CITIZEN_REPORT`, `MODEL_V5`, `UNAVAILABLE`, …).
  Nothing in a response is invented; where a value was never measured the field is
  `null` and a sibling note explains why.
- Counts are never fabricated. An absent count is `null`, not `0`.
- `SUPABASE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY` and `FIREBASE_SERVICE_ACCOUNT_JSON`
  are read server-side only and never reach the browser.
