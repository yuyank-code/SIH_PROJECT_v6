# V5 Model Integration

## Artifact
`backend/ml/v5_final_model.joblib` — a dict with keys:
- `model` → sklearn `RandomForestClassifier(n_estimators=500, max_depth=6, min_samples_leaf=5)`
- `features` → list of 13 feature names (order matters)

## Version
`v5_matched_site_no_seismic` (see `model/v5_final_report.json`)

## The 13 features (exact order)
| # | name | unit | source in this build |
|---|------|------|----------------------|
| 1 | rainfall_1d | mm | Open-Meteo daily precipitation_sum, last 1 day |
| 2 | rainfall_3d | mm | Open-Meteo, sum of last 3 days |
| 3 | rainfall_7d | mm | Open-Meteo, sum of last 7 days |
| 4 | rainfall_15d | mm | Open-Meteo, sum of last 15 days |
| 5 | rainfall_30d | mm | Open-Meteo, sum of last 30 days |
| 6 | max_rainfall_3d | mm | Open-Meteo, max rolling 3-day total inside 30d window |
| 7 | max_rainfall_7d | mm | Open-Meteo, max rolling 7-day total inside 30d window |
| 8 | rainy_days_7d | days | Open-Meteo, count of last 7 days with precipitation > 1 mm |
| 9 | elevation_m | m | zones.terrain (DEMO seed today; DEM in production) |
| 10 | slope_deg | deg | zones.terrain (DEMO today; DEM-derived slope in production) |
| 11 | aspect_sin | unitless | zones.terrain (DEMO today) |
| 12 | aspect_cos | unitless | zones.terrain (DEMO today) |
| 13 | curvature_1_m | 1/m | zones.terrain (DEMO today) |

Terrain values from the seed set are labelled `terrain_source: DEMO`. **These must be
replaced by DEM-derived values before operational use.** The model itself is not touched.

## Loading
`app/services/ml_service.py::MLService` loads the joblib bundle once at import time.
The FastAPI process holds the model in memory for the life of the container.

## Prediction
```
POST /api/predictions/predict
{"features": {"rainfall_1d": ..., ..., "curvature_1_m": ...}}
```
Response:
```
{
  "prediction": 0|1,
  "probability": 0.0..1.0,
  "risk_score": probability * 100,
  "severity": "LOW|MEDIUM|HIGH|CRITICAL",
  "model_version": "v5_matched_site_no_seismic",
  "contributing_factors": [...],
  "feature_order": [...]
}
```

Operational threshold: `0.15` (from `v5_final_report.json.threshold_choice`).
Severity bands (from `v5_threshold_analysis.csv`):

| band | probability | notes |
|------|-------------|-------|
| LOW | < 0.15 | below the balanced OOF cutoff |
| MEDIUM | 0.15 – 0.35 | matched-eval precision ~ 0.57 → 0.65 |
| HIGH | 0.35 – 0.65 | matched-eval precision ~ 0.65 → 0.81 |
| CRITICAL | ≥ 0.65 | matched-eval precision ≥ 0.81 |

Reported P/R at threshold=0.15 (matched 1:1 evaluation set): precision 0.571, recall 0.981.
Operational precision on real deployment will differ, because the model was trained on a
balanced 1:1 set (prevalence 0.5). `MLService.recalibrate()` applies the King & Zeng (2001)
log-odds prior correction to shift a probability onto a real base rate. It is shipped and
opt-in: set the `OPERATIONAL_PREVALENCE` env var (0<p<1) and `predict_one` additionally
returns `operational_probability`, `operational_risk_score`, `operational_severity`, and a
`calibration` block. The raw `probability`/`severity` fields are never altered (see report
`known_limitations_still_present`).

## Zone prediction (with feature assembly)
```
POST /api/predictions/zone
{"zone_id": "NER-001", "rainfall_override": null}
```
The risk service:
1. Fetches the zone row from Supabase (Postgres, with its stored `terrain` block).
2. Calls Open-Meteo historical archive for the last ~32 daily precipitation totals.
3. Derives the 8 rainfall features via `risk_service._rainfall_features_from_history`.
4. If `rainfall_override` is provided (used by the "simulate more rain" demo slider),
   those 8 values are substituted.
5. Calls `ml_service.predict_one(features)`.
6. Upserts the result into the `risk_predictions` table (Postgres, one row per zone).

If Open-Meteo is unavailable or the zone has no terrain, the endpoint returns
`424 feature_unavailable`. The model is **never** invoked with fabricated inputs.

## Regression tests
`backend/tests/test_ml_regression.py` verifies:
- feature list order matches the training script exactly
- `ml_service.predict_one` output equals a direct `RandomForestClassifier.predict_proba` call
  for two known samples (drift < 1e-6)
- severity band mapping produces LOW / CRITICAL for the correct inputs
- missing feature raises `ValueError`

Run:
```
cd backend && python -m pytest tests/test_ml_regression.py -q
```
