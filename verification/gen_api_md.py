#!/usr/bin/env python3
"""Regenerate API.md from the actual FastAPI route table.

API.md had drifted to documenting 27 of 81 routes. Rather than hand-patch it
(and let it drift again), the reference is derived from the code: every entry
below is read off the registered route, its signature and its docstring, so the
document cannot claim an endpoint that does not exist or miss one that does.

Re-run after adding routes:  python3 gen_api_md.py
"""
import inspect, os, re, sys, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fakedeps"))
CANDIDATES = [os.path.join(HERE, ".."),
              os.path.join(HERE, "ner-slide-v4/SIH_project-main"),
              os.path.join(HERE, "SIH_project-main")]
ROOT = next((os.path.abspath(c) for c in CANDIDATES
             if os.path.isdir(os.path.join(c, "backend", "app"))), None)
if ROOT is None:
    sys.exit("cannot locate the project root relative to this script")
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
os.environ.setdefault("SUPABASE_URL", "https://stub.supabase.co")
os.environ.setdefault("SUPABASE_SECRET_KEY", "stub")

import server
from app.auth_middleware import PUBLIC_PATHS, PUBLIC_PREFIXES

ORDER = [
    ("Health & model", ("/api/health", "/api/model", "/api/me")),
    ("Zones & GIS", ("/api/zones", "/api/gis", "/api/terrain", "/api/weather")),
    ("Sensors", ("/api/sensors",)),
    ("Citizen reporting", ("/api/reports",)),
    ("Shelters & safe routes", ("/api/shelters", "/api/safe-route")),
    ("Alerts & notifications", ("/api/alerts", "/api/notifications", "/api/recipients", "/api/push")),
    ("Response & dispatch", ("/api/response",)),
    ("Recovery", ("/api/incidents", "/api/recovery", "/api/impacts", "/api/resources")),
    ("Monitoring & live ops", ("/api/monitoring", "/api/ops")),
    ("Predictions (V5 model)", ("/api/predictions",)),
    ("Dashboard & analytics", ("/api/dashboard", "/api/analytics")),
    ("Explainability & satellite", ("/api/explain", "/api/satellite")),
    ("Public (no sign-in required)", ("/api/public",)),
]

def protection(path, fn):
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return "public"
    m = re.search(r'require_roles\(\s*"(\w+)"', inspect.getsource(fn))
    return m.group(1) if m else "signed-in"

def body_model(fn):
    """Find the request-body model in a handler signature.

    Annotations arrive as strings (deferred evaluation), so they are resolved by
    name against the server module rather than used directly.
    """
    for name, p in inspect.signature(fn).parameters.items():
        ann = p.annotation
        if isinstance(ann, str):
            ann = getattr(server, ann, None)
        if inspect.isclass(ann) and issubclass(ann, server.BaseModel) and ann is not server.BaseModel:
            return ann.__name__, ann
    return None, None

def summary(fn):
    doc = inspect.getdoc(fn) or ""
    first = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
    return re.sub(r"\s+", " ", first)

routes = []
for m, p, fn, _k in server.api.registered:
    routes.append((m, p, fn))

buckets = {label: [] for label, _ in ORDER}
buckets["Other"] = []
for m, p, fn in routes:
    placed = False
    if p.startswith("/api/public"):
        buckets["Public (no sign-in required)"].append((m, p, fn)); continue
    for label, prefixes in ORDER:
        if label.startswith("Public"):
            continue
        if any(p.startswith(x) for x in prefixes):
            buckets[label].append((m, p, fn)); placed = True; break
    if not placed:
        buckets["Other"].append((m, p, fn))

out = []
out.append("# API reference\n")
out.append(f"All {len(routes)} endpoints registered by `backend/server.py`, generated from the route\n"
           "table itself (`python3 gen_api_md.py`) so it cannot drift from the code.\n")
out.append("""
## Authentication

Every path under `/api/` requires a `Authorization: Bearer <supabase-jwt>` header
**except** the paths listed under *Public* below, which the auth middleware exempts
by prefix (`/api/public/`) or by name (`/api/health`, `/api/model/info`, `/docs`,
`/openapi.json`, `/redoc`).

The **Access** column means:

| Value | Meaning |
| --- | --- |
| `public` | no token required |
| `signed-in` | any authenticated profile, including `CITIZEN` |
| `FIELD_OFFICER` | `FIELD_OFFICER`, `AUTHORITY` or `ADMIN` |
| `AUTHORITY` | `AUTHORITY` or `ADMIN` |

Roles nest: `ADMIN ⊂ AUTHORITY ⊂ FIELD_OFFICER ⊂ signed-in`. A citizen reaching a
role-gated route gets `403`; an unauthenticated request to a non-public route gets `401`.
""")

METHOD_ORDER = {"GET": 0, "POST": 1, "PATCH": 2, "PUT": 3, "DELETE": 4}
for label in [l for l, _ in ORDER] + ["Other"]:
    rows = buckets.get(label) or []
    if not rows:
        continue
    out.append(f"\n## {label}\n")
    out.append("| Method | Path | Access | Purpose |")
    out.append("| --- | --- | --- | --- |")
    for m, p, fn in sorted(rows, key=lambda r: (r[1], METHOD_ORDER.get(r[0], 9))):
        name, model = body_model(fn)
        # A blank cell means the handler carries no docstring. Left blank on
        # purpose: inventing a description here would put text in the API
        # reference that nothing in the code actually claims.
        s = summary(fn) or "_(no description in source)_"
        if len(s) > 150:
            s = s[:147].rsplit(" ", 1)[0] + "…"
        s = s.replace("|", "\\|")
        if name:
            s = f"`{name}` body. {s}" if not s.startswith("_(no") else f"`{name}` body."
        out.append(f"| `{m}` | `{p}` | {protection(p, fn)} | {s} |")

out.append("""
## Request bodies

Field names below are the pydantic models in `backend/server.py`. A `?` marks an
optional field. Optional numeric fields default to `null`, never `0` — a missing
count means *not recorded*, and the UI renders it as such rather than implying a
value of zero.
""")
seen = set()
for m, p, fn in sorted(routes, key=lambda r: r[1]):
    name, model = body_model(fn)
    if not name or name in seen:
        continue
    seen.add(name)
    fields = []
    for f, default in model.__fields_map__.items():
        # The stub marks a required field with a sentinel object; anything with a
        # real default (including None) is optional and gets a '?'.
        required = not isinstance(default, (str, int, float, bool, type(None))) or (
            default is not None and False)
        fields.append(f"`{f}`" if required else f"`{f}?`")
    out.append(f"- **`{name}`** — {', '.join(fields)}")

out.append("""
## Conventions

- Every record and computed payload carries a `source` field naming its provenance
  (`SEED_DEMO`, `AUTHORITY`, `SENSOR`, `CITIZEN_REPORT`, `MODEL_V5`, `UNAVAILABLE`, …).
  Nothing in a response is invented; where a value was never measured the field is
  `null` and a sibling note explains why.
- Counts are never fabricated. An absent count is `null`, not `0`.
- `SUPABASE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY` and `FIREBASE_SERVICE_ACCOUNT_JSON`
  are read server-side only and never reach the browser.
""")

path = os.path.join(ROOT, "API.md")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(out).rstrip() + "\n")
print(f"wrote {path}: {len(routes)} endpoints, {len(seen)} request models")
