"""Run V5 risk predictions against Supabase zones.

Usage from backend/:
  python scripts/run_risk_predictions.py --zone NER-001
  python scripts/run_risk_predictions.py --zone NER-001 --persist
  python scripts/run_risk_predictions.py --all --persist

Without --persist this is a dry run and never writes predictions. The
--demo-rainfall flag is explicitly labelled SIMULATED and is intended only for
integration testing when Open-Meteo historical data is unavailable.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.db import supabase_repo as repo
from app.services import risk_service


DEMO_RAINFALL = {
    "rainfall_1d": 45.0,
    "rainfall_3d": 110.0,
    "rainfall_7d": 230.0,
    "rainfall_15d": 390.0,
    "rainfall_30d": 680.0,
    "max_rainfall_3d": 95.0,
    "max_rainfall_7d": 175.0,
    "rainy_days_7d": 5.0,
}


async def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--zone", help="stable zone ID such as NER-001")
    group.add_argument("--all", action="store_true", help="run every zone")
    parser.add_argument("--demo-rainfall", action="store_true", help="use clearly-labelled simulated rainfall for integration testing")
    parser.add_argument("--persist", action="store_true", help="write predictions to Supabase")
    args = parser.parse_args()

    zones = await repo.list_zones() if args.all else ([await repo.get_zone(args.zone)] if args.zone else await repo.list_zones())
    zones = [z for z in zones if z]
    if not zones:
        raise SystemExit("No matching zones")

    results = []
    failures = []
    for zone in zones:
        try:
            result = await risk_service.predict_zone(zone, DEMO_RAINFALL if args.demo_rainfall else None)
            if "error" in result:
                failures.append({"zone_id": zone["zone_id"], "error": result})
                continue
            priority = risk_service.classify_response_priority(result, zone)
            saved = await repo.upsert_prediction(zone["zone_id"], result, priority) if args.persist else None
            results.append({
                "zone_id": zone["zone_id"],
                "probability": result["probability"],
                "risk_score": result["risk_score"],
                "severity": result["severity"],
                "priority": priority["priority"],
                "model_version": result.get("model_version"),
                "rainfall_source": "DEMO_OVERRIDE" if args.demo_rainfall else "OPEN_METEO_HISTORY",
                "persisted": bool(saved),
                "prediction_id": str(saved["id"]) if saved else None,
            })
        except Exception as exc:  # noqa: BLE001
            failures.append({"zone_id": zone["zone_id"], "error": str(exc)})

    print(json.dumps({"count": len(results), "failed": len(failures), "results": results, "failures": failures}, indent=2, default=str))
    await repo.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
