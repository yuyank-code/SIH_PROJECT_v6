"""Iteration 2 regression tests — DEM terrain + SMS blast + Recipients CRUD.

Covers: DEM bootstrap idempotency on startup, /api/terrain/recompute,
notifications/status LOG_ONLY, seeded recipients, CRUD + district-scoped
SMS blast on POST /api/alerts, notifications ledger persistence, and
end-to-end run-all still green with real terrain.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

def _base_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        # Fallback: read frontend/.env
        try:
            with open("/app/frontend/.env") as fh:
                for line in fh:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    if not v:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return v.rstrip("/")


BASE_URL = _base_url()


@pytest.fixture(scope="module")
def sess() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# DEM terrain
# ---------------------------------------------------------------------------
def _wait_dem_bootstrap(sess, timeout: float = 60.0) -> None:
    """Startup fires DEM recompute in a background task — poll until at least
    a few zones flip from DEMO → DEM_OPEN_METEO (or timeout)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = sess.get(f"{BASE_URL}/api/zones/NER-001", timeout=15)
        if r.ok and r.json().get("terrain_source") == "DEM_OPEN_METEO":
            return
        time.sleep(3)


def test_dem_bootstrap_ner001(sess):
    _wait_dem_bootstrap(sess)
    r = sess.get(f"{BASE_URL}/api/zones/NER-001", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("terrain_source") == "DEM_OPEN_METEO", data.get("terrain_source")
    t = data["terrain"]
    assert isinstance(t["slope_deg"], (int, float))
    assert isinstance(t["elevation_m"], (int, float))


def test_dem_bootstrap_ner009_mountain(sess):
    r = sess.get(f"{BASE_URL}/api/zones/NER-009", timeout=15)
    assert r.status_code == 200
    data = r.json()
    # If bootstrap succeeded it should now be DEM; if throttled it may fall back
    # to DEMO — in that case call recompute explicitly.
    if data.get("terrain_source") != "DEM_OPEN_METEO":
        rr = sess.post(f"{BASE_URL}/api/terrain/recompute?zone_id=NER-009", timeout=30)
        assert rr.status_code == 200, rr.text
        assert rr.json().get("ok") >= 1
        data = sess.get(f"{BASE_URL}/api/zones/NER-009", timeout=15).json()
    t = data["terrain"]
    assert data["terrain_source"] == "DEM_OPEN_METEO"
    assert t["elevation_m"] > 1500, t
    assert t["slope_deg"] > 5, t


def test_terrain_recompute_single(sess):
    r = sess.post(f"{BASE_URL}/api/terrain/recompute?zone_id=NER-001", timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] == 1 and j["failed"] == 0
    assert j["source"] == "OPEN_METEO_ELEVATION"


def test_terrain_recompute_all(sess):
    r = sess.post(f"{BASE_URL}/api/terrain/recompute", timeout=180)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] + j["failed"] == 22
    # Real DEM should succeed for all under normal conditions
    assert j["failed"] == 0, j


# ---------------------------------------------------------------------------
# Recipients + notifications
# ---------------------------------------------------------------------------
def test_notifications_status_log_only(sess):
    r = sess.get(f"{BASE_URL}/api/notifications/status", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["provider"] == "LOG_ONLY"
    assert j["twilio_configured"] is False


def test_seeded_recipients(sess):
    r = sess.get(f"{BASE_URL}/api/recipients", timeout=15)
    assert r.status_code == 200
    rec = r.json()
    assert len(rec) >= 3
    langs = {x["language"] for x in rec}
    assert {"as", "ne", "lus"}.issubset(langs)
    # Verify Mizoram Field Officer district is null (nation-wide)
    mizo = [x for x in rec if x["language"] == "lus"][0]
    assert mizo["district"] in (None, "")


def test_recipient_crud(sess):
    payload = {
        "name": "TEST_QA Officer",
        "phone": "+919111111111",
        "role": "FIELD_OFFICER",
        "district": "Aizawl",
        "language": "lus",
    }
    r = sess.post(f"{BASE_URL}/api/recipients", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["name"] == payload["name"]
    assert created["id"]
    rid = created["id"]

    r2 = sess.get(f"{BASE_URL}/api/recipients", timeout=15)
    assert any(x["id"] == rid for x in r2.json())

    d = sess.delete(f"{BASE_URL}/api/recipients/{rid}", timeout=15)
    assert d.status_code == 200
    assert d.json() == {"deleted": 1}

    r3 = sess.get(f"{BASE_URL}/api/recipients", timeout=15)
    assert not any(x["id"] == rid for x in r3.json())


def test_alert_district_scoped_blast(sess):
    # NER-001 is East Khasi Hills → Meghalaya Ops (as) + Mizoram Field (lus, null district)
    payload = {"zone_id": "NER-001", "reason": "TEST_iter2 SMS fan-out", "severity": "HIGH"}
    r = sess.post(f"{BASE_URL}/api/alerts", json=payload, timeout=45)
    assert r.status_code == 200, r.text
    alert = r.json()
    deliveries = alert.get("deliveries", [])
    assert deliveries, "alert.deliveries missing"

    langs = sorted({d["language"] for d in deliveries})
    # Must include as + lus, must NOT include ne (Sikkim District Head)
    assert "as" in langs, langs
    assert "lus" in langs, langs
    assert "ne" not in langs, f"Sikkim should not receive East Khasi alert: {langs}"

    for d in deliveries:
        assert d["status"] == "log_only"
        assert d["provider"] == "LOG_ONLY"
        assert d["zone_id"] == "NER-001"
        assert d["phone"].startswith("+")
        assert d["body"]  # non-empty body in recipient's language


def test_notifications_persisted(sess):
    r = sess.get(f"{BASE_URL}/api/notifications?limit=20", timeout=15)
    assert r.status_code == 200
    notifs = r.json()
    assert notifs, "no notifications persisted"
    n0 = notifs[0]
    for k in ("zone_id", "phone", "language", "body", "provider", "status", "timestamp"):
        assert k in n0, f"missing field: {k}"


# ---------------------------------------------------------------------------
# Prediction regression with new DEM terrain
# ---------------------------------------------------------------------------
def test_run_all_with_dem_terrain(sess):
    r = sess.post(f"{BASE_URL}/api/predictions/run-all", timeout=120)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] == 22 and j["failed"] == 0, j
