# NER-SLIDE

AI-powered landslide early warning, monitoring, GIS, and disaster-response platform
for the North Eastern Region (NER) of India — built for Smart India Hackathon.

## What's inside
- **V5 RandomForest ML model** (13 features) loaded once at process start
- **Real weather** via Open-Meteo (forecast + historical rainfall + elevation)
- **Interactive GIS map** (Leaflet + OSM tiles) with risk zones, heatmap, roads,
  villages, sensors, reports and per-severity color coding
- **Zone detail view** with "Why is this zone at risk?" (LLM-generated
  explanation, rule-based fallback)
- **Response prioritization** (P1-P4) using severity + population + road status
- **Multilingual alerts** (English, Assamese, Khasi, Mizo, Nepali, Bodo)
- **Field officer / citizen portal** with GPS capture, photo upload, and an
  offline-first localStorage sync queue
- **Analytics** (severity distribution, priority stack, Open-Meteo 30-day rainfall)
- **Dispatch & live ops board** — task assignment plus a rolling activity feed
- **Model transparency panel** — features, thresholds and known limitations, in the UI
- **Recovery playbook** — 31 phased post-event steps, impact and resource tracking, SITREP
- **Monitoring watchboard** — per-zone staleness and coverage, so a silent sensor
  reads as *unknown* rather than *fine*
- **Citizen reporting with photos** — anyone signed in can send ground truth, with a
  corroboration signal that counts distinct reporters, and an officer triage queue
- **Safe route & shelter recommendation** — `/safety` answers "where do I go?"
  without a login: ranked shelters, movement guidance, nearby road hazards

## Quickstart
```
supervisorctl restart backend frontend
```
Backend: `http://localhost:8001/api/health`
Frontend: `http://localhost:3000/`

## Model files
Place the V5 trained artifact at `backend/ml/v5_final_model.joblib`.
Training report + threshold analysis live under `model/`.

## Data-source transparency
Every record is tagged with a `source` field (OPEN_METEO, OSM_DEMO, DEMO, etc.)
so operators can see exactly what's real and what's demo data.

## Pages

| Route | Who | What |
| --- | --- | --- |
| `/public` | anyone, no login | risk map, active alerts, and the two things that matter: *Where do I go?* and *Report what you can see* |
| `/safety` | anyone, no login | ranked shelters, ordered movement guidance, nearby road hazards |
| `/report` | any signed-in profile, CITIZEN included | GPS + photo + description, queues offline |
| `/dashboard` `/map` `/ops` `/zones` `/sensors` `/reports` `/alerts` `/response` `/shelters` `/recovery` `/model` `/analytics` | ops roles | operations surface |
| `/recipients` | AUTHORITY, ADMIN | alert recipient management |
| `/field` | FIELD_OFFICER and above | field reporting |

## Verification

```
cd verification && ./verify_v5.sh
```

Runs offline — no npm, no PyPI, no network. Compiles the backend, replays the v4
regression suite, runs 107 logic assertions, imports the real `server.py` against
stub libraries to introspect all 81 routes and their access levels, checks the
frontend/backend API seam, and balances every JSX file. Steps that need the
pre-v5 baseline tree skip loudly rather than pass. See `verification/README.md`.

## Docs
- `ARCHITECTURE.md` — modular monolith layout
- `API.md` — all 81 endpoints, generated from the route table (`python3 verification/gen_api_md.py`)
- `MODEL_INTEGRATION.md` — V5 features / thresholds / regression tests
- `DEMO.md` — 5-minute SIH demonstration script
- `FEATURES_v5_citizen_reporting_safe_routes.md` — citizen reporting + safe routes
- `FEATURES_v4_recovery_playbook_monitoring.md` — recovery playbook + monitoring
- `FEATURES_response_recovery.md` — dispatch, live ops, model transparency
