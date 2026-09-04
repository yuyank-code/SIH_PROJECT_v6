"""Full backend API regression suite for NER-SLIDE.

Covers: health, model info, prediction, run-all, dashboard, zones,
zone-level prediction override, reports side effect, alerts translations,
GIS, response priorities.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://nerslide-alert.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- Health & model ---
class TestHealth:
    def test_health(self, s):
        r = s.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["model_loaded"] is True
        assert j["model_version"] == "v5_matched_site_no_seismic"
        assert j["feature_count"] == 13

    def test_model_info(self, s):
        r = s.get(f"{BASE_URL}/api/model/info", timeout=15)
        assert r.status_code == 200
        j = r.json()
        expected = [
            "rainfall_1d", "rainfall_3d", "rainfall_7d", "rainfall_15d", "rainfall_30d",
            "max_rainfall_3d", "max_rainfall_7d", "rainy_days_7d",
            "elevation_m", "slope_deg", "aspect_sin", "aspect_cos", "curvature_1_m",
        ]
        feats = j.get("features") or j.get("feature_list") or j.get("feature_names")
        assert feats == expected, f"got {feats}"


# --- Prediction endpoint ---
class TestPredictions:
    HIGH = {
        "rainfall_1d": 200, "rainfall_3d": 400, "rainfall_7d": 600, "rainfall_15d": 900, "rainfall_30d": 1500,
        "max_rainfall_3d": 150, "max_rainfall_7d": 300, "rainy_days_7d": 7,
        "elevation_m": 900, "slope_deg": 35, "aspect_sin": 0.9, "aspect_cos": 0.1, "curvature_1_m": 0.005,
    }

    def test_predict_critical(self, s):
        r = s.post(f"{BASE_URL}/api/predictions/predict", json={"features": self.HIGH}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["severity"] == "CRITICAL"
        assert 0 < j["probability"] < 1
        cf = j.get("contributing_factors") or []
        assert len(cf) > 0

    def test_predict_missing_feature(self, s):
        bad = dict(self.HIGH)
        bad.pop("slope_deg")
        r = s.post(f"{BASE_URL}/api/predictions/predict", json={"features": bad}, timeout=30)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text[:200]}"


# --- Run all zones (Open-Meteo dependent) ---
class TestRunAll:
    def test_run_all(self, s):
        r = s.post(f"{BASE_URL}/api/predictions/run-all", timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") == 22, f"expected ok=22, got {j}"
        assert j.get("failed", 0) == 0, f"failed zones: {j}"


# --- Dashboard summary ---
class TestDashboard:
    def test_summary(self, s):
        r = s.get(f"{BASE_URL}/api/dashboard/summary", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["zones_total"] == 22
        sc = j["severity_counts"]
        total = sum(sc.get(k, 0) for k in ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
        assert total == 22, f"severity totals != 22: {sc}"


# --- Zones list & detail ---
class TestZones:
    def test_zones_list(self, s):
        r = s.get(f"{BASE_URL}/api/zones", timeout=30)
        assert r.status_code == 200
        zones = r.json()
        assert len(zones) == 22
        for z in zones:
            assert "latest" in z and z["latest"] is not None, f"missing latest on {z.get('zone_id')}"
            assert "severity" in z["latest"]
            assert "risk_score" in z["latest"]

    def test_zone_detail(self, s):
        r = s.get(f"{BASE_URL}/api/zones/NER-001", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert "terrain" in j
        assert "roads_nearby" in j
        assert "villages_nearby" in j
        assert "sensors" in j


# --- Zone-level prediction with rainfall override ---
class TestZonePredictionOverride:
    def test_override_upgrades_severity(self, s):
        payload = {
            "zone_id": "NER-001",
            "rainfall_override": {
                "rainfall_1d": 250, "rainfall_3d": 500, "rainfall_7d": 700,
                "rainfall_15d": 1000, "rainfall_30d": 1600,
                "max_rainfall_3d": 180, "max_rainfall_7d": 320, "rainy_days_7d": 7,
            },
        }
        r = s.post(f"{BASE_URL}/api/predictions/zone", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["severity"] == "CRITICAL", f"got severity {j.get('severity')}"
        rp = j.get("response_priority") or {}
        assert rp.get("priority") in ("P1", "P2"), f"got priority {rp}"


# --- Reports side-effect ---
class TestReports:
    def test_road_blockage_marks_road(self, s):
        payload = {
            "report_type": "ROAD_BLOCKAGE",
            "lat": 25.55,
            "lon": 91.85,
            "description": "TEST_ blockage from regression",
            "reporter": "TEST_regression",
        }
        r = s.post(f"{BASE_URL}/api/reports", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        assert j.get("zone_id"), f"zone_id not attached: {j}"

        # verify at least one road is BLOCKED
        r2 = s.get(f"{BASE_URL}/api/gis/roads", timeout=30)
        assert r2.status_code == 200
        roads = r2.json()
        # roads may be a FeatureCollection or a list
        if isinstance(roads, dict) and "features" in roads:
            statuses = [f.get("properties", {}).get("status") for f in roads["features"]]
        else:
            statuses = [rd.get("status") for rd in roads]
        assert "BLOCKED" in statuses, f"no BLOCKED road found: {statuses}"


# --- Alerts multilingual ---
class TestAlerts:
    def test_alert_translations(self, s):
        payload = {
            "zone_id": "NER-001",
            "severity": "HIGH",
            "reason": "TEST_ heavy rainfall predicted; landslide risk elevated.",
        }
        r = s.post(f"{BASE_URL}/api/alerts", json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        tr = j.get("translations") or {}
        for lang in ["en", "as", "kha", "lus", "ne", "brx"]:
            assert lang in tr, f"missing lang {lang}: {list(tr.keys())}"


# --- GIS ---
class TestGIS:
    def test_risk_zones_geojson(self, s):
        r = s.get(f"{BASE_URL}/api/gis/risk-zones", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j.get("type") == "FeatureCollection"
        feats = j.get("features", [])
        assert len(feats) > 0
        for f in feats:
            assert "severity" in f.get("properties", {})

    def test_heatmap(self, s):
        r = s.get(f"{BASE_URL}/api/gis/heatmap", timeout=30)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list) and len(arr) > 0
        p = arr[0]
        for k in ("lat", "lon", "intensity", "severity"):
            assert k in p, f"missing {k} in heatmap point: {p}"


# --- Response priorities ---
class TestResponse:
    def test_priorities_ordered(self, s):
        r = s.get(f"{BASE_URL}/api/response/priorities", timeout=30)
        assert r.status_code == 200
        lst = r.json()
        assert isinstance(lst, list)
        order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
        prev = 0
        for it in lst:
            p = it.get("priority")
            assert p in order, f"unexpected priority {p}"
            assert order[p] >= prev, f"out of order: {p} after rank {prev}"
            prev = order[p]
