#!/usr/bin/env python3
"""Logic checks for the v4 recovery + monitoring code.

No pytest / no network in this sandbox, so this is a self-contained harness that
imports the real modules and exercises them against fixtures. `supabase` is not
installed here either, so a minimal fake client is injected before importing the
repo — the repo's query-builder calls are then executed for real against
in-memory tables, which is what we actually want to verify (bulk fetch, joins,
idempotency), not the network layer.
"""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

# Works from either layout: beside the project tree during development, or
# inside it (verification/) as shipped in the zip.
_HERE = Path(__file__).resolve().parent
BACKEND = next((c.resolve() for c in (_HERE.parent / "backend",
                                      _HERE / "ner-slide-v4/SIH_project-main/backend",
                                      _HERE / "SIH_project-main/backend")
                if (c / "app").is_dir()), None)
if BACKEND is None:
    sys.exit("cannot locate backend/ relative to this script")
sys.path.insert(0, str(BACKEND))

FAILS = []


def check(label, cond, extra=""):
    if cond:
        print(f"  PASS  {label}")
    else:
        FAILS.append(label)
        print(f"  FAIL  {label} {extra}")


# ---------------------------------------------------------------------------
# Fake supabase layer (only what the repo actually calls)
# ---------------------------------------------------------------------------
TABLES = {"incidents": [], "zones": [], "recovery_plans": [], "recovery_steps": []}


class Res:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class Query:
    def __init__(self, table):
        self.table = table
        self.rows = list(TABLES[table])
        self._insert = None
        self._update = None
        self._single = None

    # --- read shaping ---
    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self.rows = [r for r in self.rows if r.get(col) == val]
        return self

    def in_(self, col, vals):
        self.rows = [r for r in self.rows if r.get(col) in set(vals)]
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def maybe_single(self):
        self._single = "maybe"
        return self

    def single(self):
        self._single = "one"
        return self

    # --- writes ---
    def insert(self, payload):
        self._insert = payload if isinstance(payload, list) else [payload]
        return self

    def update(self, patch):
        self._update = patch
        return self

    async def execute(self):
        if self._insert is not None:
            import uuid as _u
            created = []
            for row in self._insert:
                row = dict(row)
                row.setdefault("id", str(_u.uuid4()))
                row.setdefault("created_at", "2026-09-01T00:00:00Z")
                row.setdefault("updated_at", "2026-09-01T00:00:00Z")
                TABLES[self.table].append(row)
                created.append(row)
            return Res(created[0] if self._single else created)
        if self._update is not None:
            for r in self.rows:
                r.update(self._update)
            return Res(self.rows[0] if self._single else self.rows)
        if self._single:
            return Res(self.rows[0] if self.rows else None)
        return Res(self.rows)


class FakeClient:
    def table(self, name):
        TABLES.setdefault(name, [])
        return Query(name)

    def rpc(self, *a, **k):
        raise AssertionError("rpc should not be used by the code under test")


fake_supabase = types.ModuleType("supabase")
fake_supabase.AsyncClient = object
async def _acreate(*a, **k):
    return FakeClient()
fake_supabase.acreate_client = _acreate
sys.modules["supabase"] = fake_supabase

fake_push = types.ModuleType("app.services.push_service")
async def _send(*a, **k):
    return {"failed": 0}
fake_push.send_to_tokens = _send
sys.modules["app.services.push_service"] = fake_push

import app.data.recovery_playbook as playbook          # noqa: E402
import app.db.supabase_repo as repo                    # noqa: E402
import app.services.monitoring_service as mon          # noqa: E402

repo._client = FakeClient()
async def _client():
    return FakeClient()
repo.client = _client


# ---------------------------------------------------------------------------
print("\n[1] recovery_playbook — template shape & severity gating")
# ---------------------------------------------------------------------------
steps = playbook.STEPS
check("all four phases present",
      {s["phase"] for s in steps} == {"RELIEF", "EARLY_RECOVERY", "RESTORATION", "RESILIENCE"})
check("step codes are unique", len({s["code"] for s in steps}) == len(steps))
check("every step has guidance fields",
      all("requires_assessment" in s and "manageable_when" in s for s in steps),
      [s["code"] for s in steps if "manageable_when" not in s])

crit = playbook.build_steps("CRITICAL")
high = playbook.build_steps("HIGH")
low = playbook.build_steps("LOW")
check("CRITICAL gets every step", len(crit) == len(steps), f"{len(crit)} vs {len(steps)}")
check("LOW drops severity-gated steps", len(low) < len(high) < len(crit), f"{len(low)}/{len(high)}/{len(crit)}")
check("REL-NDRF gated out of LOW", "REL-NDRF" not in {s["code"] for s in low})
check("REL-NDRF present for HIGH", "REL-NDRF" in {s["code"] for s in high})
check("REL-MASSCAS only at CRITICAL",
      "REL-MASSCAS" in {s["code"] for s in crit} and "REL-MASSCAS" not in {s["code"] for s in high})
check("unknown severity is most inclusive", len(playbook.build_steps(None)) == len(crit))
check("build_steps carries guidance through",
      all("manageable_when" in s and "requires_assessment" in s for s in crit))
check("phase_order matches declared phase order",
      all(s["phase_order"] == ["RELIEF", "EARLY_RECOVERY", "RESTORATION", "RESILIENCE"].index(s["phase"]) for s in crit))

# ---------------------------------------------------------------------------
print("\n[2] _recovery_progress — NA excluded from denominator, never counted done")
# ---------------------------------------------------------------------------
fix = [
    {"phase": "RELIEF", "status": "DONE"},
    {"phase": "RELIEF", "status": "DONE"},
    {"phase": "RELIEF", "status": "IN_PROGRESS"},
    {"phase": "RELIEF", "status": "NA"},
    {"phase": "EARLY_RECOVERY", "status": "PENDING"},
    {"phase": "RESTORATION", "status": "NA"},
]
p = repo._recovery_progress(fix)
relief = [x for x in p["phases"] if x["phase"] == "RELIEF"][0]
resto = [x for x in p["phases"] if x["phase"] == "RESTORATION"][0]
check("RELIEF total excludes NA", relief["total"] == 3, relief)
check("RELIEF pct = 2/3 -> 67", relief["pct"] == 67, relief["pct"])
check("NA counted separately", relief["na"] == 1)
check("all-NA phase is 0/0 not a false 100%", (resto["total"], resto["done"], resto["pct"]) == (0, 0, 0), resto)
check("overall excludes NA rows", (p["overall_done"], p["overall_total"]) == (2, 4), p)
check("overall pct = 50", p["overall_pct"] == 50)
check("empty plan is 0/0 and does not divide by zero",
      repo._recovery_progress([])["overall_pct"] == 0)

# ---------------------------------------------------------------------------
print("\n[3] _current_phase — earliest phase with unfinished work")
# ---------------------------------------------------------------------------
cur = repo._current_phase(p)
check("current phase is RELIEF while relief unfinished", cur and cur["phase"] == "RELIEF", cur)
done_all = repo._recovery_progress([{"phase": "RELIEF", "status": "DONE"}])
check("None once everything is done", repo._current_phase(done_all) is None)
check("phase with only NA steps is skipped",
      repo._current_phase(repo._recovery_progress(
          [{"phase": "RELIEF", "status": "NA"}, {"phase": "EARLY_RECOVERY", "status": "PENDING"}]
      ))["phase"] == "EARLY_RECOVERY")

# ---------------------------------------------------------------------------
print("\n[4] generate_recovery_plan — idempotent, progress-preserving")
# ---------------------------------------------------------------------------
async def scenario():
    TABLES["incidents"] = [{"id": "inc-1", "title": "Sonapur slope failure", "status": "ACTIVE",
                            "severity": "HIGH", "occurred_at": "2026-08-30T05:00:00Z",
                            "source": "AUTHORITY", "zones": {"zone_id": "Z1", "name": "Sonapur",
                                                             "state": "Assam", "district": "Kamrup"}},
                           {"id": "inc-2", "title": "Minor cut slope", "status": "CONTAINED",
                            "severity": "LOW", "occurred_at": "2026-08-20T05:00:00Z",
                            "source": "AUTHORITY", "zones": {"zone_id": "Z2", "name": "Dawki",
                                                             "state": "Meghalaya", "district": "Jaintia"}}]
    TABLES["recovery_plans"], TABLES["recovery_steps"] = [], []

    plan = await repo.generate_recovery_plan("inc-1", "HIGH", None)
    n_first = len(plan["steps"])
    check("plan generated with the HIGH step set", n_first == len(high), f"{n_first} vs {len(high)}")
    check("template steps tagged source=TEMPLATE", all(s["source"] == "TEMPLATE" for s in plan["steps"]))
    check("guidance persisted on generated rows",
          all("manageable_when" in s for s in plan["steps"]))
    check("every generated step starts PENDING", all(s["status"] == "PENDING" for s in plan["steps"]))

    # work two steps, then re-generate
    first = plan["steps"][0]
    await repo.update_recovery_step(first["id"], {"status": "DONE"})
    await repo.update_recovery_step(plan["steps"][1]["id"], {"status": "NA"})
    again = await repo.generate_recovery_plan("inc-1", "HIGH", None)
    check("re-generate adds no duplicates", len(again["steps"]) == n_first, len(again["steps"]))
    codes = [s["code"] for s in again["steps"]]
    check("codes still unique after re-generate", len(set(codes)) == len(codes))
    kept = [s for s in again["steps"] if s["id"] == first["id"]][0]
    check("existing progress preserved across re-generate", kept["status"] == "DONE", kept["status"])
    check("done_at stamped on DONE", bool(kept.get("done_at")))

    # a severity upgrade should top up the missing steps, not reset
    upgraded = await repo.generate_recovery_plan("inc-1", "CRITICAL", None)
    check("severity upgrade tops up missing steps", len(upgraded["steps"]) == len(crit),
          f"{len(upgraded['steps'])} vs {len(crit)}")
    still = [s for s in upgraded["steps"] if s["id"] == first["id"]][0]
    check("top-up still preserves worked steps", still["status"] == "DONE")

    # reverting a DONE step clears done_at
    reverted = await repo.update_recovery_step(first["id"], {"status": "IN_PROGRESS"})
    check("done_at cleared when leaving DONE", reverted.get("done_at") is None, reverted.get("done_at"))

    # manual step
    manual = await repo.add_recovery_step(upgraded["id"], {"title": "Rebuild the footbridge",
                                                           "phase": "RESTORATION",
                                                           "requires_assessment": True})
    check("manual step tagged MANUAL", manual["source"] == "MANUAL")
    check("manual step gets a MANUAL- code", manual["code"].startswith("MANUAL-"), manual["code"])
    check("manual requires_assessment honoured", manual["requires_assessment"] is True)

    # ---------------- overview ----------------
    ov = await repo.recovery_overview()
    check("overview returns a row per incident", len(ov) == 2, len(ov))
    r1 = [r for r in ov if r["incident_id"] == "inc-1"][0]
    r2 = [r for r in ov if r["incident_id"] == "inc-2"][0]
    check("incident without a plan reports plan=None (not 0%)", r2["plan"] is None)
    check("overview progress matches the detail page",
          r1["plan"]["progress"] == (await repo.get_recovery_plan("inc-1"))["progress"])
    check("overview names the current phase", r1["plan"]["current_phase"]["phase"] == "RELIEF",
          r1["plan"]["current_phase"])
    all_steps = await repo.list_recovery_steps(r1["plan"]["id"])
    expect_await = len([s for s in all_steps if s.get("requires_assessment")
                        and s.get("status") in ("PENDING", "IN_PROGRESS")])
    check("awaiting_assessment counts open on-ground steps",
          r1["plan"]["awaiting_assessment"] == expect_await,
          f'{r1["plan"]["awaiting_assessment"]} vs {expect_await}')
    check("overview carries zone context", r1["zone_name"] == "Sonapur" and r1["district"] == "Kamrup")
    check("overview keeps incident source", r1["source"] == "AUTHORITY")

asyncio.run(scenario())

# ---------------------------------------------------------------------------
print("\n[5] monitoring_service — watch levels, trend, staleness")
# ---------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone as tz
now = datetime.now(tz.utc)
iso = lambda h: (now - timedelta(hours=h)).isoformat()

preds = [
    {"zone_id": "Z1", "zone_name": "Sonapur", "state": "Assam", "district": "Kamrup",
     "severity": "CRITICAL", "probability": 0.91, "predicted_at": iso(1),
     # 30mm in the last 3 days against 180mm in the 4 before it -> the storm has
     # passed, so FALLING. (Severity stays CRITICAL: the slope is still loaded.)
     "features_used": {"rainfall_3d": 30.0, "rainfall_7d": 210.0}},
    {"zone_id": "Z2", "zone_name": "Dawki", "state": "Meghalaya", "district": "Jaintia",
     "severity": "MEDIUM", "probability": 0.55, "predicted_at": iso(2),
     "features_used": {"rainfall_3d": 150.0, "rainfall_7d": 170.0}},   # rising -> escalates
    {"zone_id": "Z3", "zone_name": "Cherra", "state": "Meghalaya", "district": "East Khasi",
     "severity": "LOW", "probability": 0.12, "predicted_at": iso(30)},  # stale, no features
]
rows = mon.build_watchboard(preds)
by = {r["zone_id"]: r for r in rows}
check("one row per prediction", len(rows) == 3)
check("CRITICAL zone is on WARNING", by["Z1"]["watch_level"] == "WARNING", by["Z1"]["watch_level"])
check("every row has an action cue", all(r.get("cue") for r in rows))
check("every row explains itself (rationale)", all(r.get("rationale") for r in rows))
check("falling rain detected", by["Z1"]["trend"] == "FALLING", by["Z1"]["trend"])
check("rising rain detected", by["Z2"]["trend"] == "RISING", by["Z2"]["trend"])
check("MEDIUM + RISING escalates", by["Z2"]["escalated"] is True and by["Z2"]["watch_level"] == "WARNING",
      (by["Z2"]["watch_level"], by["Z2"]["escalated"]))
check("no features -> trend UNKNOWN, not a fabricated number", by["Z3"]["trend"] == "UNKNOWN")
check("old prediction flagged stale", by["Z3"]["stale"] is True and by["Z3"]["age_hours"] >= 24,
      by["Z3"]["age_hours"])
check("fresh prediction not stale", by["Z1"]["stale"] is False)
check("recent_3d_mm passed through", by["Z1"]["trend_detail"]["recent_3d_mm"] == 30.0,
      by["Z1"]["trend_detail"])
check("prior_4d_mm derived as 7d-3d", by["Z1"]["trend_detail"]["prior_4d_mm"] == 180.0,
      by["Z1"]["trend_detail"])
check("trend_detail carries a source tag", bool(by["Z3"]["trend_detail"].get("source")))

# direct unit checks on the trend rule itself
check("comparable halves -> STEADY",
      mon.rainfall_trend({"rainfall_3d": 100.0, "rainfall_7d": 200.0})["trend"] == "STEADY")
check("dry week does not read as RISING",
      mon.rainfall_trend({"rainfall_3d": 0.0, "rainfall_7d": 0.0})["trend"] != "RISING")
check("partial features -> UNKNOWN, never a guess",
      mon.rainfall_trend({"rainfall_3d": 90.0})["trend"] == "UNKNOWN")
check("UNKNOWN trend is tagged UNAVAILABLE, not DERIVED",
      mon.rainfall_trend({})["source"] == "UNAVAILABLE")

summ = mon.watchboard_summary(rows)
check("summary counts zones monitored", summ["zones_monitored"] == 3)
check("summary counts WARNING zones", summ["by_level"]["WARNING"] == 2, summ["by_level"])
check("summary counts stale zones", summ["stale_zones"] == 1)
check("summary publishes the staleness threshold", summ.get("stale_after_hours"))
check("by_level totals equal the row count", sum(summ["by_level"].values()) == 3, summ["by_level"])

# empty input must not explode
check("empty watchboard is safe", mon.build_watchboard([]) == [])
check("empty summary is safe", mon.watchboard_summary([])["zones_monitored"] == 0)

# ---------------------------------------------------------------------------
print("\n" + ("ALL LOGIC CHECKS PASSED" if not FAILS else f"{len(FAILS)} FAILURE(S): {FAILS}"))
sys.exit(1 if FAILS else 0)
