# verification/

Everything needed to re-check this build without a network, a package index, or a
browser. Run it from here:

```
cd verification && ./verify_v5.sh
```

## Why this exists in this shape

The environment this code was reviewed in had no npm, no PyPI and no outbound
network. That rules out `pytest`, a CRA build, and a live Supabase. Rather than
declare the work unverified, the checks were built to run against what is
actually present: the source itself.

The approach that made the difference is `fakedeps/` — a stub tree standing in
for fastapi, pydantic, starlette, supabase, httpx, joblib and google-auth. With
it on `sys.path`, the **real** `backend/server.py` imports and its route table
can be introspected. That catches what grep cannot: a duplicate `(method, path)`
registration, a handler calling a repo function that does not exist, a literal
path shadowed by a parameterised sibling, a module-scope `NameError`, and whether
each route's actual protection matches its documented intent.

The stubs are deliberately unhelpful where being helpful would be dishonest. The
fake estimator raises if anything tries to score with it, and the fake feature
list is read from the checked-in `model/v5_final_report.json` rather than
invented — so the harness cannot quietly validate against model behaviour that
does not exist.

## The seven steps

| Step | What it proves |
| --- | --- |
| 1 backend compiles | no syntax errors anywhere under `backend/` |
| 2 v4 suite | the recovery/monitoring logic from v4 still behaves (no regression) |
| 3 v5 logic checks | 107 assertions over geometry, shelter ranking, corroboration, triage, capacity handling |
| 4 route table | real `server.py` imported against stubs; 81 routes, protections match intent |
| 5 static checks | icon names, dead imports, every `api.*` path resolves to a route, no secret names in `frontend/src` |
| 6 JSX balance | brackets, braces and tags balance in every frontend file |
| 7 ML surface | the model files are byte-identical to the pre-v5 baseline |

## Steps that need the v3 baseline

Two checks compare against the untouched pre-v5 tree: step 7 (proving the ML
surface was not touched) and the icon-name attestation inside step 5 (with no npm,
the only evidence a phosphor name is valid in this exact version is that the
previous build already imported it and compiled).

That baseline is a development artifact and is **not** shipped here. When it is
absent those checks **skip loudly** rather than pass. A check that goes green
because its input went missing is worse than one that admits it did not run.
Everything else runs fully from inside the package.

## Regenerating the API reference

```
python3 gen_api_md.py
```

Reads the live FastAPI route table and rewrites `../API.md` — real paths, real
access levels resolved through both the auth middleware and each `require_roles`
gate, real docstrings. It cannot claim an endpoint that does not exist or miss
one that does. Re-run after adding routes.

## What none of this covers

A real browser render, live Supabase queries, and actual model scoring. Those
need a machine with the dependencies installed. The checks here narrow what can
be wrong; they do not replace running the thing.
