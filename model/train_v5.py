import pandas as pd, numpy as np, json, joblib
from sklearn.model_selection import GroupKFold
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, precision_recall_curve, fbeta_score, accuracy_score, precision_score, recall_score, f1_score
from sklearn.inspection import permutation_importance
from sklearn.base import clone

df = pd.read_csv("landslide_v5_matched_dataset.csv", parse_dates=["DATE"])

FEATURES = [
    "rainfall_1d","rainfall_3d","rainfall_7d","rainfall_15d","rainfall_30d",
    "max_rainfall_3d","max_rainfall_7d","rainy_days_7d",
    "elevation_m","slope_deg","aspect_sin","aspect_cos","curvature_1_m",
]
X = df[FEATURES].to_numpy()
y = df["landslide"].to_numpy()
groups = df["pair_id"].to_numpy()   # matched pair = spatial+site group, never split across folds

models = {
    "LogisticRegression": Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, C=1.0))]),
    "RandomForest": RandomForestClassifier(n_estimators=500, max_depth=6, min_samples_leaf=5, random_state=42, n_jobs=-1),
    "HistGradientBoosting": HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, l2_regularization=1.0, random_state=42),
}

gkf = GroupKFold(n_splits=5)
results = {}
oof_preds = {name: np.zeros(len(y)) for name in models}

for name, model in models.items():
    fold_metrics = []
    for tr_idx, te_idx in gkf.split(X, y, groups):
        mdl = clone(model)
        mdl.fit(X[tr_idx], y[tr_idx])
        p = mdl.predict_proba(X[te_idx])[:,1]
        oof_preds[name][te_idx] = p
        fold_metrics.append({
            "roc_auc": roc_auc_score(y[te_idx], p),
            "pr_auc": average_precision_score(y[te_idx], p),
            "brier": brier_score_loss(y[te_idx], p),
        })
    fm = pd.DataFrame(fold_metrics)
    results[name] = {
        "roc_auc_mean": fm.roc_auc.mean(), "roc_auc_std": fm.roc_auc.std(),
        "pr_auc_mean": fm.pr_auc.mean(), "pr_auc_std": fm.pr_auc.std(),
        "brier_mean": fm.brier.mean(), "brier_std": fm.brier.std(),
        "folds": fold_metrics,
    }
    print(name, {k:v for k,v in results[name].items() if k!="folds"})

# ---- Temporal holdout: hold out most recent pairs by positive event year ----
pair_year = df[df.landslide==1].set_index("pair_id")["year"]
years_sorted = pair_year.sort_values()
n_test_pairs = int(0.25*len(years_sorted))
test_pairs = set(years_sorted.index[-n_test_pairs:])
test_mask = df["pair_id"].isin(test_pairs).to_numpy()
train_mask = ~test_mask
test_years = sorted(df.loc[test_mask, "year"].unique().tolist())
print("Temporal holdout pairs:", n_test_pairs, "years touched:", test_years)

temporal_results = {}
for name, model in models.items():
    mdl = clone(model)
    mdl.fit(X[train_mask], y[train_mask])
    p = mdl.predict_proba(X[test_mask])[:,1]
    pred = (p>=0.5).astype(int)
    temporal_results[name] = {
        "roc_auc": roc_auc_score(y[test_mask], p),
        "pr_auc": average_precision_score(y[test_mask], p),
        "accuracy": accuracy_score(y[test_mask], pred),
        "precision": precision_score(y[test_mask], pred),
        "recall": recall_score(y[test_mask], pred),
        "f1": f1_score(y[test_mask], pred),
        "brier": brier_score_loss(y[test_mask], p),
        "n": int(test_mask.sum()),
    }
    print(name, temporal_results[name])

json.dump({"spatial_cv": results, "temporal_holdout": {"test_years": test_years, "results": temporal_results}},
          open("v5_cv_results.json","w"), indent=2, default=float)

# Save OOF preds for threshold tuning + permutation importance
np.save("oof_preds_hgb.npy", oof_preds["HistGradientBoosting"])
np.save("y.npy", y)
np.save("groups.npy", groups)
df.to_pickle("df_full.pkl")
print("saved CV artifacts")
