"""V5 Landslide Risk ML Inference Service.

Loads the trained RandomForestClassifier V5 model ONCE at process start and
provides typed predict() calls. Feature order and thresholds come directly
from the shipped joblib bundle and v5_final_report.json / v5_threshold_analysis.csv
— nothing is fabricated.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

log = logging.getLogger("ml_service")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = BACKEND_ROOT / "ml" / "v5_final_model.joblib"
REPO_MODEL_DIR = BACKEND_ROOT.parent / "model"

# Severity thresholds derived from v5_threshold_analysis.csv.
# 0.15 is the report's "balanced OOF" operating point (recall=0.98).
# Bands chosen from that same curve:
#   <0.15  LOW      (recall would exceed 0.98 -> too many false alerts to raise)
#   0.15-0.35 MEDIUM  (precision 0.57 -> 0.65)
#   0.35-0.65 HIGH   (precision 0.65 -> 0.81)
#   >=0.65 CRITICAL (precision 0.81+)
SEVERITY_BANDS = [
    ("LOW", 0.0, 0.15),
    ("MEDIUM", 0.15, 0.35),
    ("HIGH", 0.35, 0.65),
    ("CRITICAL", 0.65, 1.01),
]


class MLService:
    def __init__(self, model_path: Optional[Path] = None) -> None:
        self.model_path = Path(model_path or os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))
        self.model = None
        self.features: List[str] = []
        self.version: str = "v5_matched_site_no_seismic"
        self.report: Dict[str, Any] = {}
        # Prior-correction config (see recalibrate()). The model was trained on a
        # balanced 1:1 matched set, so train_prevalence defaults to 0.5. Set the
        # OPERATIONAL_PREVALENCE env var (0<p<1) to also emit prior-corrected
        # probabilities for a realistic monsoon site-day base rate.
        self.train_prevalence: float = 0.5
        self.operational_prevalence: Optional[float] = None
        self._load()

    def _load(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"V5 model not found at {self.model_path}")
        bundle = joblib.load(self.model_path)
        # Bundle format: {"model": RandomForestClassifier, "features": [...]}
        self.model = bundle["model"]
        self.features = list(bundle["features"])
        report_path = REPO_MODEL_DIR / "v5_final_report.json"
        if report_path.exists():
            self.report = json.loads(report_path.read_text())
            self.version = self.report.get("version", self.version)
            dataset = self.report.get("dataset") or {}
            positives, total = dataset.get("positives_kept"), dataset.get("total_rows")
            if positives and total:
                self.train_prevalence = float(positives) / float(total)
        env_prevalence = os.environ.get("OPERATIONAL_PREVALENCE", "").strip()
        if env_prevalence:
            try:
                value = float(env_prevalence)
                if 0.0 < value < 1.0:
                    self.operational_prevalence = value
                else:
                    log.warning("OPERATIONAL_PREVALENCE must be in (0,1); ignoring %r", env_prevalence)
            except ValueError:
                log.warning("ignoring invalid OPERATIONAL_PREVALENCE=%r", env_prevalence)
        log.info("Loaded V5 model=%s features=%d version=%s train_prevalence=%.3f",
                 type(self.model).__name__, len(self.features), self.version, self.train_prevalence)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def feature_list(self) -> List[str]:
        return list(self.features)

    def transparency(self) -> Dict[str, Any]:
        """Structured, honest 'what this model does and does not do' summary.

        Every number is read from the shipped artifacts (v5_final_report.json /
        v5_threshold_analysis.csv) or the code constants — nothing is invented.
        Powers the read-only model-transparency panel in the UI.
        """
        report = self.report or {}
        dataset = report.get("dataset") or {}
        return {
            "version": self.version,
            "task": "Binary landslide-occurrence probability for a zone, given recent rainfall + terrain",
            "algorithm": "RandomForestClassifier (scikit-learn)",
            "features": self.feature_list(),
            "feature_count": len(self.features),
            "operating_threshold": {
                "value": 0.15,
                "chosen_for": "Balanced out-of-fold operating point (recall ~0.98)",
                "source": "v5_threshold_analysis.csv",
            },
            "severity_bands": [{"label": x[0], "lo": x[1], "hi": x[2]} for x in SEVERITY_BANDS],
            "training": {
                "design": "Matched-pair 1:1 (each positive landslide site paired with a nearby negative)",
                "train_prevalence": round(self.train_prevalence, 4),
                "positives_kept": dataset.get("positives_kept"),
                "total_rows": dataset.get("total_rows"),
                "note": ("Balanced training prevalence (~0.5) overstates absolute risk versus a rare "
                         "real base rate. Enable OPERATIONAL_PREVALENCE to also emit prior-corrected "
                         "probabilities."),
                "source": "v5_final_report.json",
            },
            "calibration": {
                "enabled": self.operational_prevalence is not None,
                "operational_prevalence": self.operational_prevalence,
                "method": "king_zeng_2001_logit_shift",
            },
            "global_importance": report.get("permutation_importance_random_forest_oof") or {},
            "importance_source": (
                "permutation_importance_random_forest_oof (v5_final_report.json)"
                if report.get("permutation_importance_random_forest_oof") else "unavailable"
            ),
            "not_designed_for": [
                "Predicting the exact timing or pixel-location of a slope failure — it is a risk score, not a trigger.",
                "Sub-zone / individual-parcel prediction — it operates at zone granularity.",
                "Non-rainfall triggers such as earthquakes — seismic features were deliberately excluded in V5.",
                "Replacing field verification or official GSI / IMD / SDMA warnings — it complements them.",
            ],
            "sources": {
                "thresholds": "v5_threshold_analysis.csv",
                "importances": "v5_final_report.json",
                "baselines": "NER monsoon-terrain domain heuristics (documented in ml_service._explain)",
            },
        }

    def severity_from_prob(self, p: float) -> str:
        for label, lo, hi in SEVERITY_BANDS:
            if lo <= p < hi:
                return label
        return "CRITICAL"

    @staticmethod
    def recalibrate(prob: float, target_prevalence: float, train_prevalence: float = 0.5) -> float:
        """Prior-correct a probability from the training prior to a real base rate.

        The V5 model was trained on a balanced 1:1 matched-pair set (prevalence
        0.5), so its raw probabilities overstate risk relative to a real monsoon
        site-day, where events are rare. This applies the standard log-odds shift
        (King & Zeng, 2001):

            logit' = logit(p) + ln[ (target/(1-target)) / (train/(1-train)) ]

        Returns the corrected probability in (0, 1). It does NOT change the raw
        `probability` the model reports; it is exposed separately so operators can
        threshold against a realistic base rate — the step v5_final_report.json
        (`known_limitations_still_present`) says must be applied before deployment.
        """
        eps = 1e-9
        p = min(max(float(prob), eps), 1.0 - eps)
        target = min(max(float(target_prevalence), eps), 1.0 - eps)
        train = min(max(float(train_prevalence), eps), 1.0 - eps)
        logit = math.log(p / (1.0 - p))
        logit += math.log((target / (1.0 - target)) / (train / (1.0 - train)))
        return 1.0 / (1.0 + math.exp(-logit))

    def predict_one(self, features_dict: Dict[str, float]) -> Dict[str, Any]:
        # Enforce exact feature set + order.
        missing = [f for f in self.features if f not in features_dict]
        if missing:
            raise ValueError(f"missing_features:{missing}")
        row = np.array([[float(features_dict[f]) for f in self.features]], dtype=float)
        proba = float(self.model.predict_proba(row)[0, 1])
        pred = int(proba >= 0.15)  # operational threshold from V5 report
        severity = self.severity_from_prob(proba)
        contributing = self._explain(features_dict, proba)
        result: Dict[str, Any] = {
            "prediction": pred,
            "probability": round(proba, 6),
            "risk_score": round(proba * 100.0, 2),
            "severity": severity,
            "model_version": self.version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contributing_factors": contributing,
            "feature_order": self.features,
        }
        # Optional prior-corrected view. The raw fields above are left untouched
        # so existing consumers and regression tests see identical values;
        # operators opt in by setting OPERATIONAL_PREVALENCE to a real base rate.
        if self.operational_prevalence is not None:
            op = self.recalibrate(proba, self.operational_prevalence, self.train_prevalence)
            result["operational_probability"] = round(op, 6)
            result["operational_risk_score"] = round(op * 100.0, 2)
            result["operational_severity"] = self.severity_from_prob(op)
            result["calibration"] = {
                "train_prevalence": round(self.train_prevalence, 6),
                "operational_prevalence": round(self.operational_prevalence, 6),
                "method": "king_zeng_2001_logit_shift",
                "source": "PRIOR_CORRECTION",
            }
        return result

    def _explain(self, feats: Dict[str, float], proba: float) -> List[Dict[str, Any]]:
        """Per-prediction driver attribution — no fabricated data.

        Global permutation importances (from v5_final_report.json) tell us which
        features matter across the dataset, but not which ones are elevated for
        *this* input. We combine both: a feature contributes only when its value
        exceeds a benign baseline, scaled by how far toward (and past) a domain
        "concern" level it sits, weighted by the model's importance for that
        feature:

            norm         = clamp((value - baseline) / (concern - baseline), 0, 1.5)
            contribution = importance * norm

        Features at or below baseline are omitted (norm = 0), so a genuinely calm
        site returns an empty list rather than invented risk. Baselines/concern
        levels are monsoon-terrain heuristics for NER, not model outputs, so they
        are reported as such. Returns the top 5 drivers, strongest first.
        """
        importances = (self.report.get("permutation_importance_random_forest_oof") or {})
        # (feature, human label, unit, benign_baseline, concern_level)
        specs = [
            ("rainfall_1d", "Rainfall (last 24h)", "mm", 5, 40),
            ("rainfall_3d", "Rainfall (last 3 days)", "mm", 15, 100),
            ("rainfall_7d", "Rainfall (last 7 days)", "mm", 30, 200),
            ("rainfall_15d", "Rainfall (last 15 days)", "mm", 60, 350),
            ("rainfall_30d", "Rainfall (last 30 days)", "mm", 120, 600),
            ("max_rainfall_3d", "Peak 3-day rainfall in window", "mm", 15, 80),
            ("max_rainfall_7d", "Peak 7-day rainfall in window", "mm", 30, 150),
            ("rainy_days_7d", "Rainy days in last 7 days", "days", 1, 4),
            ("slope_deg", "Terrain slope", "deg", 5, 20),
            ("elevation_m", "Elevation", "m", 500, 1800),
        ]
        drivers: List[Dict[str, Any]] = []
        for key, label, unit, baseline, concern in specs:
            value = float(feats.get(key, 0.0))
            span = float(concern - baseline) or 1.0
            norm = (value - baseline) / span
            norm = min(max(norm, 0.0), 1.5)
            if norm <= 0.0:
                continue
            importance = float(importances.get(key, 0.0))
            drivers.append({
                "feature": key,
                "label": label,
                "value": round(value, 2),
                "unit": unit,
                "importance": importance,
                "contribution": round(importance * norm, 6),
                "exceeds_alert": value >= concern,
            })

        drivers.sort(key=lambda d: (d["contribution"], d["importance"]), reverse=True)
        return drivers[:5]


# Singleton – loaded once at import
ml_service = MLService()
