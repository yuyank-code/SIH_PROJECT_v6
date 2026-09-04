"""Regression test: verify V5 model outputs match a fixed reference.

Run: `pytest -q backend/tests/test_ml_regression.py`
"""
import os
import sys
from pathlib import Path

import numpy as np
import joblib

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.services.ml_service import ml_service


def test_feature_list_exact():
    assert ml_service.feature_list() == [
        "rainfall_1d", "rainfall_3d", "rainfall_7d", "rainfall_15d", "rainfall_30d",
        "max_rainfall_3d", "max_rainfall_7d", "rainy_days_7d",
        "elevation_m", "slope_deg", "aspect_sin", "aspect_cos", "curvature_1_m",
    ]


def test_model_matches_direct_sklearn_call():
    bundle = joblib.load(BACKEND / "ml" / "v5_final_model.joblib")
    model = bundle["model"]
    samples = [
        {"rainfall_1d": 0, "rainfall_3d": 2, "rainfall_7d": 5, "rainfall_15d": 20, "rainfall_30d": 60,
         "max_rainfall_3d": 1, "max_rainfall_7d": 3, "rainy_days_7d": 1,
         "elevation_m": 500, "slope_deg": 5, "aspect_sin": 0.0, "aspect_cos": 1.0, "curvature_1_m": 0.0},
        {"rainfall_1d": 200, "rainfall_3d": 400, "rainfall_7d": 600, "rainfall_15d": 900, "rainfall_30d": 1500,
         "max_rainfall_3d": 150, "max_rainfall_7d": 300, "rainy_days_7d": 7,
         "elevation_m": 900, "slope_deg": 35, "aspect_sin": 0.9, "aspect_cos": 0.1, "curvature_1_m": 0.005},
    ]
    for s in samples:
        row = np.array([[s[f] for f in ml_service.feature_list()]], dtype=float)
        expected = float(model.predict_proba(row)[0, 1])
        got = ml_service.predict_one(s)["probability"]
        assert abs(got - expected) < 1e-6, f"drift: got {got} vs {expected}"


def test_severity_bands():
    # LOW when very low signal
    r = ml_service.predict_one({"rainfall_1d": 0, "rainfall_3d": 2, "rainfall_7d": 5, "rainfall_15d": 20, "rainfall_30d": 60,
                                "max_rainfall_3d": 1, "max_rainfall_7d": 3, "rainy_days_7d": 1,
                                "elevation_m": 500, "slope_deg": 5, "aspect_sin": 0.0, "aspect_cos": 1.0, "curvature_1_m": 0.0})
    assert r["severity"] == "LOW"
    # CRITICAL when huge signal
    r2 = ml_service.predict_one({"rainfall_1d": 200, "rainfall_3d": 400, "rainfall_7d": 600, "rainfall_15d": 900, "rainfall_30d": 1500,
                                 "max_rainfall_3d": 150, "max_rainfall_7d": 300, "rainy_days_7d": 7,
                                 "elevation_m": 900, "slope_deg": 35, "aspect_sin": 0.9, "aspect_cos": 0.1, "curvature_1_m": 0.005})
    assert r2["severity"] == "CRITICAL"


def test_missing_feature_raises():
    import pytest
    with pytest.raises(ValueError):
        ml_service.predict_one({"rainfall_1d": 1})
