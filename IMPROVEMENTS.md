# Improvements — code review pass (2026-08-31)

A focused review of the NER-SLIDE codebase. Every change is surgical, keeps the
V5 feature contract intact, and leaves the regression tests green. No model
inputs are fabricated — the project rule that every payload carries a `source`
field is preserved throughout.

## 1. Fixed a duplicate-CORS middleware bug (correctness)

**Problem.** `CORSMiddleware` was being added twice — once inside
`app/auth_middleware.py` and once in `server.py`. Starlette inserts each
`add_middleware` at the *top* of the stack, so two CORS layers ran in sequence
and emitted duplicate `Access-Control-Allow-Origin` headers. Browsers reject a
response with two such headers, so cross-origin calls from the deployed frontend
could fail intermittently.

**Fix.** Removed the CORS block from `auth_middleware.py` (it now installs only
the auth layer). `server.py` adds a single `CORSMiddleware` *after*
`include_router`, making it the outermost layer so preflight `OPTIONS` and
`401/403` auth responses still carry CORS headers. The allow-list is overridable
via the `CORS_ORIGINS` env var. Both files now carry a comment explaining the
ordering so the bug can't quietly return.

## 2. Shipped the `recalibrate()` prior correction the docs promised (correctness)

**Problem.** `v5_final_report.json` lists as a known limitation that
"the `recalibrate()` prior-correction step must be applied with a real
prevalence estimate before operational deployment," and `MODEL_INTEGRATION.md`
referenced `recalibrate()` — but no such function existed. The model is trained
on a balanced 1:1 matched set (prevalence 0.5), so its raw probabilities
overstate risk against a real, rare-event base rate.

**Fix.** Added `MLService.recalibrate()`, the standard King & Zeng (2001)
log-odds shift:

```
logit' = logit(p) + ln[ (target/(1-target)) / (train/(1-train)) ]
```

It is **opt-in and non-breaking**: set `OPERATIONAL_PREVALENCE` (0<p<1) and
`predict_one` additionally returns `operational_probability`,
`operational_risk_score`, `operational_severity`, and a `calibration` block
(tagged `source: PRIOR_CORRECTION`). The raw `probability`/`risk_score`/
`severity` fields are never altered, so existing consumers and the regression
tests are unaffected. The training prevalence is read from the report's dataset
block (`positives_kept / total_rows` = 320/640 = 0.5), not hard-coded.

## 3. Strengthened per-prediction explainability (quality)

**Problem.** `_explain()` flagged a feature only when its raw value crossed a
single hard threshold, then ranked purely by *global* importance. That mixes two
different questions ("does this feature matter in general?" vs. "is it elevated
*now*?") and could under-explain a genuinely risky prediction.

**Fix.** `_explain()` now computes a local contribution per feature —
`importance × clamp((value − baseline)/(concern − baseline), 0, 1.5)` — so a
factor surfaces only when it is actually elevated for *this* input, weighted by
how much the model relies on it. Each driver reports its `contribution` and an
`exceeds_alert` flag, sorted strongest-first (top 5). A calm site returns an
empty list rather than invented risk. Baselines are documented as
NER monsoon-terrain heuristics, not model outputs.

## 4. Aligned stale documentation with the Supabase architecture (clarity)

The backend migrated from MongoDB to Supabase/PostGIS, but several docs and one
docstring still described the old store. Updated `ARCHITECTURE.md` (data-store
adapter section + diagram), `MODEL_INTEGRATION.md` (zone-prediction flow now
reads/writes the Postgres `risk_predictions` table; `recalibrate()` note now
reflects the shipped, opt-in behavior), and the `sms_service.py` docstring
(`notifications`/`recipients` are Postgres tables). Historical migration
provenance in the adapter docstrings was left intact.

## 5. Removed dead code in the training script (hygiene)

`model/train_v5.py` had a no-op line (`m = joblib.parallel.clone if False else
None`) and re-imported `sklearn.base.clone` inside two loops. Hoisted a single
`from sklearn.base import clone` to the top and dropped the dead line.

## 6. Fixed multilingual alerts showing identical text in every language (correctness)

**Problem.** The alert language selector on the Alerts page appeared to do
nothing — switching between English, Assamese, Khasi, Mizo, Nepali, and Bodo
showed the *same* text every time. Root cause: the old `translate_alert()`
helper only produced real translations when an LLM key was configured; with no
key (the default), its fallback path wrote the **English string into all six
language slots**. The UI selector was working correctly — it was faithfully
switching between six identical copies.

**Fix.** Rewrote `backend/app/services/llm_service.py` around a new
`build_alert_translations()` that composes each alert from structured parts and
layers sources safest-first:

1. **Verified offline templates** for English, Assamese, and Nepali
   (`builtin_verified`). These are hand-authored, localize the fixed safety
   scaffolding (severity word, "landslide risk near", the Reason/Action
   labels) into the correct script, and work with **no LLM key and no network**
   — so language switching is genuinely functional out of the box.
2. **LLM extension** to the lower-resource NER languages (Khasi, Mizo, Bodo)
   only when a key is present, tagged `llm`.
3. **Honest English fallback** (`en_fallback`) when neither is available, so an
   untranslated language is clearly marked "pending" rather than silently
   passed off as a translation.

Each alert now carries a `_sources` map (nested inside the existing
`translations` JSONB, so **no schema migration** is needed) recording the
provenance of every language. `frontend/src/pages/Alerts.jsx` shows a
provenance chip per language ("Verified" / "Auto-translated" / "English
(pending translation)").

**Deliberately not hand-faked.** Khasi/Mizo/Bodo emergency text is *not*
hand-authored, because mistranslating a safety warning is more dangerous than
honestly marking it pending (a quick check confirmed, e.g., that Mizo *tlang*
means "hill," not "landslide"). Those languages are covered by the LLM when a
key is configured and clearly tagged otherwise. This keeps the project's
"never fabricate; every payload carries a source" rule intact for
safety-critical text.

## 7. Made the database reproducible from the repo (reliability)

**Problem.** `supabase/migrations/` contained only RLS policies, indexes, and
grants — **no `CREATE TABLE` or `CREATE FUNCTION`**. The 17 tables and 8 PostGIS
RPCs the backend depends on existed only inside the live Supabase project (built
via the dashboard). A fresh project — a new demo environment, a teammate cloning
the repo, or disaster recovery — had nothing to run, and the backend would fail
to start.

**Fix.** Added `supabase/schema.sql`, reconstructed from what the code actually
reads and writes (`supabase_repo.py`, `migration_seed.py`, `auth_service.py`,
`device_service.py`, and the columns referenced by the existing RLS policies).
It defines the extensions (pgcrypto, postgis), all 17 tables with correct types
and foreign keys, the auth helper functions and triggers the policies assume
(`current_user_role()`, `is_authority()`, `handle_new_user()`, `set_updated_at()`),
and the 8 RPCs (`list_zones_geojson`, `nearby_roads`, …) whose return shapes were
cross-checked column-by-column against the Python mappers. A `supabase/README.md`
documents the exact run order (schema → hardening migrations → seed). The file is
idempotent and safe on an empty project.

**Note.** None of the *code* improvements in this changelog require a schema
change — this item is purely about being able to recreate the database from the
repo. If you already have a working Supabase project, you don't need to run it;
diff before applying to anything with data.

## Verification

- All edited Python files byte-compile cleanly (`py_compile`).
- The new `recalibrate()`, `_explain()`, and `predict_one` operational-field
  logic were unit-checked in isolation (25 assertions) against the exact samples
  used by `backend/tests/test_ml_regression.py`, confirming: prior correction is
  monotonic, identity at prevalence 0.5, and clamped to (0,1); a calm site yields
  no drivers while an extreme site yields correctly-ranked ones; and raw
  probability/severity are byte-for-byte unchanged whether or not calibration is
  enabled.
- The multilingual fix was verified offline (no LLM key, no network):
  `build_alert_translations()` returns three genuinely distinct strings for
  en/as/ne (Assamese and Nepali in their correct non-Latin scripts), tags
  kha/lus/brx as `en_fallback`, preserves place names verbatim, and still
  returns all six language keys — so `test_api_regression.py::test_alert_translations`
  (which asserts all six keys are present) stays green.
- The full `pytest backend/tests/` suite (which loads the joblib model) should be
  run in an environment with `backend/requirements.txt` installed
  (scikit-learn 1.9.0 / numpy 2.4.6 / joblib 1.5.3); the offline review sandbox
  has no PyPI access, so the model-loading tests were verified by construction
  rather than executed here.
- `supabase/schema.sql` was validated structurally (balanced dollar-quotes,
  parentheses, and begin/commit; 17 tables and all 8 code-required RPCs present)
  and its RPC return columns were cross-checked against every field the
  `supabase_repo.py` mappers destructure — no missing columns. Postgres/PostGIS
  aren't installable in the offline sandbox, so it was not executed against a live
  database; run it on a fresh Supabase project (or diff against an existing one).
