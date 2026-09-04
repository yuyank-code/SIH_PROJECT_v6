"""Stub joblib. load() returns a bundle in the real shape, with the feature list
read from the checked-in v5 report so nothing about the model is invented — the
only fake part is the estimator, which no route under test actually scores with.
"""
import json, os, pathlib

class _StubForest:
    """Stands in for the RandomForestClassifier. Deliberately refuses to score:
    if a route under test ever reaches predict_proba, that is a finding, not
    something the harness should paper over with a made-up probability."""
    n_estimators = 300
    def predict_proba(self, X):
        raise AssertionError("stub estimator: a route tried to score the model")
    def predict(self, X):
        raise AssertionError("stub estimator: a route tried to score the model")

def load(path, *a, **k):
    # Works from either layout: this file beside the project tree during
    # development, or inside it (verification/fakedeps/) as shipped.
    here = pathlib.Path(__file__).resolve().parent.parent
    report = next((c for c in (here.parent / "model/v5_final_report.json",
                               here / "ner-slide-v4/SIH_project-main/model/v5_final_report.json",
                               here / "SIH_project-main/model/v5_final_report.json")
                   if c.is_file()), None)
    if report is None:
        raise AssertionError("stub joblib: cannot find v5_final_report.json for the real feature list")
    features = json.loads(report.read_text())["feature_list"]
    if isinstance(features, dict):
        features = list(features)
    return {"model": _StubForest(), "features": list(features)}

def dump(*a, **k): pass
