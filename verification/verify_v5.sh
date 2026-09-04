#!/bin/bash
# One command to re-verify the v5 work.
#
# Runs from either layout: beside the project tree during development, or from
# inside it (verification/) as shipped in the zip. Steps that need the untouched
# v3 baseline for diffing are skipped, loudly, when no baseline is present --
# the zip ships without one, and a check that silently passes because its input
# vanished is worse than one that admits it did not run.
set -o pipefail
cd "$(dirname "$0")"

if [ -d "../backend/app" ]; then
  NEW=..                                  # shipped layout: verification/ inside the project
elif [ -d "ner-slide-v4/SIH_project-main/backend/app" ]; then
  NEW=ner-slide-v4/SIH_project-main       # dev layout
elif [ -d "SIH_project-main/backend/app" ]; then
  NEW=SIH_project-main
else
  echo "cannot locate the project root relative to this script"; exit 2
fi

OLD=""
for cand in ../../../SIH_project-main SIH_project-main; do
  if [ -d "$cand/backend/app" ] && [ "$(cd "$cand" && pwd)" != "$(cd "$NEW" && pwd)" ]; then
    OLD=$cand; break
  fi
done

rc=0
step () { echo; echo "############ $1"; }
skip () { echo "  SKIP  $1"; }

step "1/7 backend compiles"
python3 -m compileall -q "$NEW/backend" && echo "clean" || rc=1

step "2/7 v4 regression suite still green"
python3 v4_logic_checks.py 2>&1 | tail -2 || rc=1

step "3/7 v5 logic checks"
python3 v5_logic_checks.py 2>&1 | tail -3 || rc=1

step "4/7 v5 route table (real server.py imported against stubs)"
python3 v5_route_import.py 2>&1 | tail -3 || rc=1

step "5/7 v5 static checks (icons, dead imports, api path map, secrets)"
python3 v5_static_checks.py 2>&1 | tail -2 || rc=1

step "6/7 JSX balance"
if [ -n "$OLD" ]; then
  FILES=$(diff -rq "$OLD/frontend/src" "$NEW/frontend/src" 2>/dev/null \
    | sed -E 's/^Files .* and (.*) differ$/\1/; s/^Only in (.*): (.*)$/\1\/\2/' | grep -E '\.(js|jsx)$')
  echo "  (changed/new files vs baseline)"
else
  FILES=$(find "$NEW/frontend/src" -name '*.js' -o -name '*.jsx' | sort)
  echo "  (no baseline -- checking every frontend file)"
fi
python3 jsxcheck.py $FILES 2>&1 | tail -2 || rc=1

step "7/7 ML surface unchanged vs baseline"
if [ -z "$OLD" ]; then
  skip "needs the v3 baseline tree; not shipped in the package"
else
  for f in app/services/ml_service.py scripts/run_risk_predictions.py tests/test_ml_regression.py; do
    cmp -s "$OLD/backend/$f" "$NEW/backend/$f" && echo "  identical  $f" || { echo "  CHANGED    $f"; rc=1; }
  done
  cmp -s "$OLD/backend/ml/v5_final_model.joblib" "$NEW/backend/ml/v5_final_model.joblib" \
    && echo "  identical  ml/v5_final_model.joblib" || { echo "  CHANGED    model binary"; rc=1; }
fi

echo; echo "############"
[ $rc -eq 0 ] && echo "V5 VERIFICATION: ALL GREEN" || echo "V5 VERIFICATION: FAILURES ABOVE"
exit $rc
