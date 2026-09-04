# NER-SLIDE PRD

## Original problem
SIH build: AI-powered landslide early-warning, GIS, and disaster-response
platform for the North Eastern Region of India, wrapped around an existing
trained V5 RandomForest model (13 features).

## User personas
- Authority / district officer — map-first ops console (default landing).
- Field officer — mobile-first, offline-first reporting (GPS + photo + type).
- Citizen — simplified public dashboard with local risk + emergency instructions.
- Admin — full dashboard + feedback ledger.

## Static requirements
- V5 model must be loaded once at process start; features preserved exactly.
- No fabricated data. Every payload carries a `source` field.
- Multilingual alerts (en, as, kha, lus, ne, brx).
- Offline-first reports with idempotent client_uuid dedup.
- GIS = primary UI element, not decoration.

## What's implemented (2026-02-29 build 1)
- Full backend at `/app/backend/server.py` with all `/api/*` routes.
- V5 model loaded via `app/services/ml_service.py`; 4 regression tests pass.
- Weather provider abstraction with Open-Meteo forecast + archive + elevation.
- Risk service assembles features from Open-Meteo history + stored zone terrain.
- P1..P4 response priority classifier with explicit known/unknown factor list.
- LLM helpers (Claude via Emergent Universal Key) for risk explanations + 6-language alert translation, with rule-based fallback.
- 22 seeded NER demo zones across all 8 states, plus roads / villages / sensors.
- React frontend: Login, Dashboard (map-first), Risk Map, Zones, Zone Detail (with "simulate rainfall" slider + "issue alert"), Sensors, Reports, Alerts (language switcher), Response board, Analytics, Public portal, Field Officer mobile UI (GPS + photo + offline queue).
- Docs: README, ARCHITECTURE, API, MODEL_INTEGRATION, DEMO.

## Prioritized backlog
- **P1**  Real DEM-derived terrain (replace DEMO seed) — swap `zone.terrain` values.
- **P1**  Supabase adapter (Auth + PostGIS + Storage) alongside Mongo.
- **P2**  Real MQTT/LoRaWAN sensor ingestion; wire `POST /api/sensors/readings` to alert engine.
- **P2**  Copernicus Sentinel-2 change detection layer (currently stubbed).
- **P2**  Push notifications via FCM + SMS via MSG91/Twilio; today only alert records are written.
- **P3**  Overpass batch import → OSM road & village data seeded into DB (currently 6 demo roads / 9 demo villages).
- **P3**  IMD provider once credentials arrive.

## Deferred design guidelines followed
- Cabinet Grotesk headings, IBM Plex Sans body, JetBrains Mono for data — no Inter/Roboto.
- Severity color language enforced (green/amber/orange/red).
- Sharp corners, structural borders, no purple gradients.
- Permanent map legend + text labels beside color chips.
