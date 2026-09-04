#!/usr/bin/env python3
"""v5 logic checks — citizen reporting + safe route / shelter recommendation.

Runs with no third-party dependencies (no sklearn/numpy/supabase available in
this sandbox), so it exercises the pure-logic modules directly. Anything that
would need a live Supabase connection is verified by static path-mapping in
verify_v5.sh instead.
"""
import math
import sys
from datetime import datetime, timedelta, timezone

import os
# Works from either layout: beside the project tree during development, or
# inside it (verification/) as shipped in the zip.
HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.path.join(HERE, "..", "backend"),
              os.path.join(HERE, "ner-slide-v4/SIH_project-main/backend"),
              os.path.join(HERE, "SIH_project-main/backend")]
BACKEND = next((os.path.abspath(c) for c in CANDIDATES
                if os.path.isdir(os.path.join(c, "app"))), None)
if BACKEND is None:
    sys.exit("cannot locate backend/ relative to this script")
sys.path.insert(0, BACKEND)

from app.services import safe_route_service as S
from app.services import citizen_service as C
from app.data.ner_seed import NER_SHELTERS

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def approx(a, b, tol):
    return a is not None and abs(a - b) <= tol


print("\n== geometry ==")
# Known great-circle distances, checked against published figures.
# Guwahati (26.1445, 91.7362) -> Shillong (25.5788, 91.8933): ~63-64 km
d = S.haversine_km(26.1445, 91.7362, 25.5788, 91.8933)
check("haversine Guwahati->Shillong ~63km", approx(d, 63.5, 2.0), f"got {d:.2f}")
# One degree of longitude at the equator. The often-quoted 111.32 km assumes the
# equatorial radius (6378.137 km); the module uses the IUGG *mean* radius, which
# gives 111.195 km. Mean radius is the right choice for a spherical haversine
# over hill terrain, so the expectation is pinned to it rather than to the
# equatorial figure — asserting 111.32 here would fail a correct implementation.
d2 = S.haversine_km(0.0, 0.0, 0.0, 1.0)
check("haversine 1deg lon at equator ~111.195km (mean radius)", approx(d2, 111.195, 0.01), f"got {d2:.3f}")
check("haversine uses IUGG mean radius", abs(S.EARTH_RADIUS_KM - 6371.0088) < 1e-6)
check("haversine identity is zero", S.haversine_km(25.0, 91.0, 25.0, 91.0) == 0.0)
# Symmetry
check("haversine symmetric",
      abs(S.haversine_km(25, 91, 27, 93) - S.haversine_km(27, 93, 25, 91)) < 1e-9)

check("bearing due north = 0", approx(S.bearing_deg(25, 91, 26, 91), 0.0, 0.01))
check("bearing due east ~90", approx(S.bearing_deg(0, 0, 0, 1), 90.0, 0.01))
check("bearing due south = 180", approx(S.bearing_deg(26, 91, 25, 91), 180.0, 0.01))
check("compass N", S.compass_point(0) == "N")
check("compass NE", S.compass_point(45) == "NE")
check("compass SW", S.compass_point(225) == "SW")
check("compass wraps 360->N", S.compass_point(360) == "N")
check("compass None passes through", S.compass_point(None) is None)

print("\n== walking estimates ==")
check("4km at 4km/h = 60min", S.walk_estimate_minutes(4.0) == 60)
check("walk None for unknown distance", S.walk_estimate_minutes(None) is None)
# Regression: the bug that produced "4001 min" for a 267 km shelter.
check("no walk estimate beyond walkable radius",
      S.walk_estimate_minutes(267.0) is None,
      "a 267km walk must not be presented as a walking time")
check("walkable radius boundary still walks",
      S.walk_estimate_minutes(S.WALKABLE_RADIUS_KM) is not None)

print("\n== distance penalty must never saturate (regression) ==")
near = S.assess_shelter(25.29, 91.72, {"shelter_id": "A", "name": "near", "lat": 25.2985, "lon": 91.7250,
                                       "status": "OPEN", "capacity": 250, "current_occupancy": 40})
far = S.assess_shelter(25.29, 91.72, {"shelter_id": "B", "name": "far", "lat": 25.1055, "lon": 94.3630,
                                      "status": "OPEN", "capacity": 350, "current_occupancy": 60})
check("near shelter outscores a 260km one", near["suitability"] > far["suitability"],
      f"near={near['suitability']} far={far['suitability']}")
check("far shelter flagged requires_transport", far["requires_transport"] is True)
check("near shelter not flagged transport", near["requires_transport"] is False)
# Two distant shelters at different distances must still be distinguishable.
f1 = S.assess_shelter(25.29, 91.72, {"shelter_id": "C", "name": "40km", "lat": 25.65, "lon": 91.72, "status": "OPEN"})
f2 = S.assess_shelter(25.29, 91.72, {"shelter_id": "D", "name": "300km", "lat": 27.9, "lon": 91.72, "status": "OPEN"})
check("distance keeps discriminating past the old 10km cap",
      f1["suitability"] > f2["suitability"], f"40km={f1['suitability']} 300km={f2['suitability']}")

print("\n== status & capacity handling ==")
closed = S.assess_shelter(25.29, 91.72, {"shelter_id": "E", "name": "shut", "lat": 25.30, "lon": 91.73, "status": "CLOSED"})
check("closed shelter is not reachable", closed["reachable"] is False)
check("closed shelter scores 0", closed["suitability"] == 0)
full = S.assess_shelter(25.29, 91.72, {"shelter_id": "F", "name": "full", "lat": 25.30, "lon": 91.73,
                                       "status": "FULL", "capacity": 100, "current_occupancy": 100})
check("full shelter still reachable", full["reachable"] is True)
check("full shelter warns", any("FULL" in w for w in full["warnings"]))

unknown_cap = S._capacity_view({"capacity": None, "current_occupancy": None})
check("missing capacity is not known", unknown_cap["known"] is False)
check("missing capacity has no headroom", unknown_cap["headroom"] is None)
check("missing capacity says so", "not recorded" in unknown_cap["note"].lower())
uncounted = S._capacity_view({"capacity": 200, "current_occupancy": None})
check("uncounted occupancy is not known", uncounted["known"] is False)
check("uncounted occupancy never implies empty", uncounted["headroom"] is None,
      "headroom must not be derived from a missing count")
known = S._capacity_view({"capacity": 200, "current_occupancy": 50})
check("known capacity computes headroom", known["headroom"] == 150 and known["known"] is True)

print("\n== risk zones ==")
zones = [{"zone_id": "Z1", "name": "Scarp", "centroid": {"lat": 25.295, "lon": 91.718},
          "terrain": {"elevation_m": 1400}, "latest": {"severity": "CRITICAL", "probability": 0.88}}]
z = S.nearest_risk_zone(25.29, 91.72, zones)
check("nearest zone found", z is not None and z["zone_id"] == "Z1")
check("nearest zone carries severity", z["severity"] == "CRITICAL")
check("no zone beyond radius", S.nearest_risk_zone(10.0, 70.0, zones) is None)
noprediction = [{"zone_id": "Z2", "name": "Quiet", "centroid": {"lat": 25.295, "lon": 91.718}, "latest": {}}]
z2 = S.nearest_risk_zone(25.29, 91.72, noprediction)
check("zone without prediction is UNAVAILABLE not safe", z2["source"] == S.SOURCE_UNAVAILABLE)
check("_elevation_of reads nested terrain", S._elevation_of(zones[0]) == 1400)
check("_elevation_of reads flat row", S._elevation_of({"elevation_m": 900}) == 900)
check("_elevation_of tolerates None", S._elevation_of(None) is None)

print("\n== road hazards ==")
roads = [{"road_id": "R1", "name": "NH-206", "status": "BLOCKED", "distance_km": 1.2},
         {"road_id": "R2", "name": "Link", "status": "OPEN", "distance_km": 0.4},
         {"road_id": "R3", "name": "Spur", "status": "RESTRICTED", "distance_km": 2.0},
         {"road_id": "R4", "name": "Far", "status": "BLOCKED", "distance_km": 50.0},
         {"road_id": "R5", "name": "Unsurveyed", "status": "UNKNOWN", "distance_km": 0.1}]
h = S.road_hazards(roads)
ids = [x["road_id"] for x in h]
check("open road is not a hazard", "R2" not in ids)
check("unknown road is not a hazard", "R5" not in ids)
check("blocked road is a hazard", "R1" in ids)
check("restricted road is a hazard", "R3" in ids)
check("distant hazard filtered by radius", "R4" not in ids)
check("blocked sorts before restricted", ids[0] == "R1")

print("\n== ranking & recommendation ==")
shelters = [{**{k: v for k, v in s.items() if k != "location"},
             "lat": s["location"]["lat"], "lon": s["location"]["lon"]} for s in NER_SHELTERS]
rec = S.build_recommendation(25.29, 91.72, shelters, roads, zones, limit=6)
check("ranks are 1..n in order", [s["rank"] for s in rec["shelters"]] == list(range(1, len(rec["shelters"]) + 1)))
check("recommendation is walkable", rec["recommended"]["requires_transport"] is False)
check("recommendation is reachable", rec["recommended"]["reachable"] is True)
check("recommended is within 15km", rec["recommended"]["distance_km"] <= S.WALKABLE_RADIUS_KM)
check("not flagged transport_only when a walkable option exists", rec["transport_only"] is False)
check("closed shelters sort below open ones",
      all(not s["reachable"] or True for s in rec["shelters"])
      and [s["reachable"] for s in rec["shelters"]] == sorted([s["reachable"] for s in rec["shelters"]], reverse=True))
check("every shelter lists its reasons", all(s["reasons"] for s in rec["shelters"]))
check("assumptions publish the walkable radius", rec["assumptions"]["walkable_radius_km"] == S.WALKABLE_RADIUS_KM)
check("assumptions disclaim routing", "no routing engine" in rec["assumptions"]["routing"].lower())
check("counts include walkable", "shelters_walkable" in rec["counts"])

far_rec = S.build_recommendation(27.0, 95.5, shelters, [], zones, limit=3)
check("remote origin flags transport_only", far_rec["transport_only"] is True)
check("remote origin still names an option", far_rec["recommended"] is not None)
then_head = [g for g in far_rec["guidance"] if g["code"] == "THEN_HEAD"][0]["text"]
check("transport_only guidance says do not walk", "do not set out on foot" in then_head.lower())

empty = S.build_recommendation(25.29, 91.72, [], roads, zones)
check("no shelters -> no recommendation", empty["recommended"] is None)
check("no shelters -> not transport_only", empty["transport_only"] is False)
check("no shelters -> guidance still returned", len(empty["guidance"]) > 0)

print("\n== movement guidance ==")
g = S.movement_guidance("CRITICAL", S.road_hazards(roads), True)
codes = [x["code"] for x in g]
check("critical origin evacuates first", codes[0] == "EVACUATE_NOW")
check("lateral move precedes heading to shelter", codes.index("MOVE_LATERAL") < codes.index("THEN_HEAD"))
check("blocked road appended", "ROAD_BLOCKED" in codes)
check("priorities ascend", [x["priority"] for x in g] == sorted(x["priority"] for x in g))
g_low = S.movement_guidance("LOW", [], True)
check("low severity does not shout evacuate", "EVACUATE_NOW" not in [x["code"] for x in g_low])
g_none = S.movement_guidance(None, [], False)
check("no shelter -> generic safe-ground advice",
      "open, level, firm ground" in [x for x in g_none if x["code"] == "THEN_HEAD"][0]["text"])

print("\n== citizen corroboration ==")
now = datetime.now(timezone.utc)
iso = lambda h: (now - timedelta(hours=h)).isoformat()
base = {"lat": 25.29, "lon": 91.72, "report_type": "LANDSLIDE", "status": "SUBMITTED"}
one = [{**base, "reporter_id": "u1", "created_at": iso(1)}]
check("single reporter -> SINGLE", C.corroboration(25.29, 91.72, one)["signal"] == "SINGLE")

same_user = [{**base, "reporter_id": "u1", "created_at": iso(1)},
             {**base, "reporter_id": "u1", "created_at": iso(2)},
             {**base, "reporter_id": "u1", "created_at": iso(3)}]
r = C.corroboration(25.29, 91.72, same_user)
check("one user reporting thrice is still one witness", r["distinct_reporters"] == 1, f"got {r['distinct_reporters']}")
check("one user reporting thrice is not CORROBORATED", r["signal"] == "SINGLE")

two_users = [{**base, "reporter_id": "u1", "created_at": iso(1)},
             {**base, "reporter_id": "u2", "created_at": iso(2)}]
check("two reporters -> CORROBORATED", C.corroboration(25.29, 91.72, two_users)["signal"] == "CORROBORATED")

verified = [{**base, "reporter_id": "u1", "status": "VERIFIED", "created_at": iso(1)}]
check("one verified report -> CONFIRMED", C.corroboration(25.29, 91.72, verified)["signal"] == "CONFIRMED")
check("verification outranks volume",
      C.corroboration(25.29, 91.72, verified)["signal"] == "CONFIRMED"
      and C.corroboration(25.29, 91.72, two_users)["signal"] == "CORROBORATED")

rejected = [{**base, "reporter_id": "u1", "status": "REJECTED", "created_at": iso(1)},
            {**base, "reporter_id": "u2", "status": "DUPLICATE", "created_at": iso(1)}]
check("rejected and duplicate reports never vote", C.corroboration(25.29, 91.72, rejected)["signal"] == "NONE")

stale = [{**base, "reporter_id": "u1", "created_at": iso(100)},
         {**base, "reporter_id": "u2", "created_at": iso(200)}]
check("reports outside the window are excluded", C.corroboration(25.29, 91.72, stale)["signal"] == "NONE")

distant = [{**base, "lat": 30.0, "lon": 95.0, "reporter_id": "u1", "created_at": iso(1)}]
check("reports outside the radius are excluded", C.corroboration(25.29, 91.72, distant)["signal"] == "NONE")

anon = [{**base, "reporter_id": None, "created_at": iso(1)},
        {**base, "reporter_id": None, "created_at": iso(2)},
        {**base, "reporter_id": None, "created_at": iso(3)}]
check("anonymous reports count once collectively",
      C.corroboration(25.29, 91.72, anon)["distinct_reporters"] == 1)
check("no reports -> NONE", C.corroboration(25.29, 91.72, [])["signal"] == "NONE")
check("corroboration is source-tagged", C.corroboration(25.29, 91.72, one)["source"] == C.SIGNAL_SOURCE)

print("\n== zone corroboration ==")
zc = C.zone_corroboration(zones, two_users)
check("zone with reports is returned", len(zc) == 1 and zc[0]["zone_id"] == "Z1")
check("zone corroboration carries severity", zc[0]["severity"] == "CRITICAL")
check("zones with no reports are omitted, not zeroed", C.zone_corroboration(zones, []) == [])

print("\n== triage ==")
p = C.triage_patch("VERIFIED", "checked on site", actor_id="officer-1")
check("verify sets status", p["status"] == "VERIFIED")
check("verify stamps who", p["verified_by"] == "officer-1")
check("verify stamps when", p["verified_at"] is not None)
check("verify keeps the note", p["verification_note"] == "checked on site")
pr = C.triage_patch("REJECTED", "no evidence found", actor_id="officer-1")
check("rejection is stamped too", pr["verified_at"] is not None and pr["verified_by"] == "officer-1")
ps = C.triage_patch("SUBMITTED", actor_id="officer-1")
check("reopening clears the decision stamp", ps["verified_at"] is None and ps["verified_by"] is None)
pi = C.triage_patch("ACTIONED", "dispatched", incident_id="inc-9", actor_id="o1")
check("incident link is set when provided", pi["incident_id"] == "inc-9")
check("incident link omitted when not provided", "incident_id" not in p)
try:
    C.triage_patch("NONSENSE")
    check("invalid status rejected", False, "no exception raised")
except ValueError as e:
    check("invalid status rejected", "invalid_report_status" in str(e))
for s in C.STATUSES:
    check(f"status {s} accepted", C.triage_patch(s)["status"] == s)

print("\n== triage summary ==")
summ = C.triage_summary([{"status": "SUBMITTED"}, {"status": "SUBMITTED", "media_count": 2},
                         {"status": "VERIFIED"}, {"status": "REJECTED"}])
check("summary totals", summ["total"] == 4)
check("summary counts backlog", summ["awaiting_triage"] == 2)
check("summary counts photos", summ["with_photo"] == 1)
check("summary covers every status key", set(C.STATUSES) <= set(summ["by_status"]))

print("\n== seed integrity ==")
check("13 demo shelters", len(NER_SHELTERS) == 13)
check("every shelter tagged SEED_DEMO", all(s["source"] == "SEED_DEMO" for s in NER_SHELTERS))
check("shelter ids unique", len({s["shelter_id"] for s in NER_SHELTERS}) == len(NER_SHELTERS))
check("all statuses valid", all(s["status"] in {"OPEN", "FULL", "CLOSED", "STANDBY"} for s in NER_SHELTERS))
check("all categories valid",
      all(s["category"] in {"RELIEF_CAMP", "SCHOOL", "COMMUNITY_HALL", "HOSPITAL", "HELIPAD", "OTHER"}
          for s in NER_SHELTERS))
check("coords inside NER bbox",
      all(22 <= s["location"]["lat"] <= 29 and 88 <= s["location"]["lon"] <= 96 for s in NER_SHELTERS))
check("some shelters deliberately lack capacity",
      any(s["capacity"] is None for s in NER_SHELTERS))
check("occupancy never exceeds capacity where both known",
      all(s["current_occupancy"] <= s["capacity"] for s in NER_SHELTERS
          if s["capacity"] is not None and s["current_occupancy"] is not None))

print(f"\n{'=' * 60}")
print(f"{CHECKS[0]} checks, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print(f"  FAILED: {f}")
    sys.exit(1)
print("ALL v5 LOGIC CHECKS PASSED")
