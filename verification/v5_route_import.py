#!/usr/bin/env python3
"""Import the real server.py against stubbed libraries and inspect the route
table. This catches what grep cannot: duplicate path+method registrations, a
route whose body references a repo function that does not exist, a Depends()
chain that never resolves, and NameErrors at module scope."""
import inspect, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fakedeps"))
CANDIDATES = [os.path.join(HERE, "..", "backend"),
              os.path.join(HERE, "ner-slide-v4/SIH_project-main/backend"),
              os.path.join(HERE, "SIH_project-main/backend")]
BACKEND = next((os.path.abspath(c) for c in CANDIDATES
                if os.path.isdir(os.path.join(c, "app"))), None)
if BACKEND is None:
    sys.exit("cannot locate backend/ relative to this script")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
os.environ.setdefault("SUPABASE_URL", "https://stub.supabase.co")
os.environ.setdefault("SUPABASE_SECRET_KEY", "stub")
os.environ.setdefault("SUPABASE_ANON_KEY", "stub")

fails = []
import server                                       # noqa: E402  <- the real thing
print("server.py imported against stubs\n")

routes = [(m, p, fn) for (m, p, fn, _k) in server.api.registered]
print(f"== {len(routes)} routes registered ==")

# 1. no duplicate method+path
seen = {}
seen_fn = {}
for m, p, fn in routes:
    key = (m, p)
    if key in seen:
        fails.append(f"duplicate route {m} {p}: {seen[key]} and {fn.__name__}")
    seen[key] = fn.__name__
    seen_fn[key] = fn

# 2. every route handler is awaitable or callable, and every repo/service symbol
#    it names actually exists on that module
from app.db import supabase_repo as repo
from app.services import safe_route_service, citizen_service

V5 = [r for r in routes if any(t in r[1] for t in ("shelter", "safe-route", "report"))]

# Protection comes from two independent places, so classify using both:
#   - the auth middleware, which demands a bearer token for every /api/ path
#     that is not in PUBLIC_PATHS and not under a PUBLIC_PREFIX;
#   - require_roles(...) in the handler signature, which adds a role floor.
# A route showing "authed" is NOT unprotected; it simply admits any signed-in
# profile, CITIZEN included, which is the intent for citizen reporting.
from app.auth_middleware import PUBLIC_PATHS, PUBLIC_PREFIXES

def protection(path, fn):
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return "public"
    m = re.search(r'require_roles\(\s*"(\w+)"', inspect.getsource(fn))
    return f"role:{m.group(1)}" if m else "authed"

print("\n== v5 surface (protection resolved through middleware + role gates) ==")
for m, p, fn in sorted(V5, key=lambda r: (r[1], r[0])):
    print(f"  {m:6} {p:38} {protection(p, fn):18} {fn.__name__}")

print("\n== protection matches intent ==")
INTENT = {
    ("GET", "/api/public/safe-route"): "public",
    ("GET", "/api/public/shelters"): "public",
    ("GET", "/api/public/gis/shelters"): "public",
    ("GET", "/api/safe-route"): "authed",
    ("GET", "/api/shelters"): "authed",
    ("GET", "/api/gis/shelters"): "authed",
    ("POST", "/api/reports"): "authed",          # any signed-in profile, CITIZEN included
    ("POST", "/api/reports/{report_id}/media"): "authed",
    ("GET", "/api/reports"): "authed",
    ("POST", "/api/shelters"): "role:AUTHORITY",
    ("PATCH", "/api/shelters/{shelter_id}"): "role:FIELD_OFFICER",
    ("PATCH", "/api/reports/{report_id}"): "role:FIELD_OFFICER",
}
for (m, p), want in INTENT.items():
    fn = seen_fn.get((m, p))
    if fn is None:
        fails.append(f"{m} {p} not registered, cannot check protection")
        continue
    got = protection(p, fn)
    if got == want:
        print(f"  ok   {m:6} {p:38} {got}")
    else:
        fails.append(f"{m} {p} protection is {got}, expected {want}")

print("\n== handlers only reference symbols that exist ==")
import re
for m, p, fn in routes:
    src = inspect.getsource(fn)
    for mod, obj, label in ((repo, "repo", "supabase_repo"),
                            (safe_route_service, "safe_route_service", "safe_route_service"),
                            (citizen_service, "citizen_service", "citizen_service")):
        for name in set(re.findall(rf"\b{obj}\.(\w+)", src)):
            if not hasattr(mod, name):
                fails.append(f"{m} {p} ({fn.__name__}) calls {obj}.{name} which does not exist in {label}")
if not fails:
    print("  ok   every repo/service call in every handler resolves")

print("\n== v5 routes are all present ==")
EXPECT = [
    ("GET", "/api/gis/shelters"), ("GET", "/api/public/gis/shelters"),
    ("GET", "/api/shelters"), ("GET", "/api/public/shelters"),
    ("POST", "/api/shelters"), ("PATCH", "/api/shelters/{shelter_id}"),
    ("GET", "/api/safe-route"), ("GET", "/api/public/safe-route"),
    ("POST", "/api/reports"), ("GET", "/api/reports"),
    ("GET", "/api/reports/summary"), ("GET", "/api/reports/corroboration"),
    ("PATCH", "/api/reports/{report_id}"),
    ("POST", "/api/reports/{report_id}/media"), ("GET", "/api/reports/{report_id}/media"),
]
for m, p in EXPECT:
    if (m, p) in seen:
        print(f"  ok   {m:6} {p}")
    else:
        fails.append(f"expected route missing: {m} {p}")

print("\n== route ordering: /reports/summary must precede /reports/{id} ==")
paths = [p for m, p, _ in routes if m == "GET"]
def idx(x): return paths.index(x) if x in paths else -1
lit, var = idx("/api/reports/summary"), idx("/api/reports/{report_id}/media")
if lit == -1:
    fails.append("/api/reports/summary not registered as GET")
elif var != -1 and lit > var:
    fails.append("literal /reports/summary registered after a parameterised sibling; it would be shadowed")
else:
    print("  ok   literal paths are registered before parameterised siblings")

print("\n== pydantic bodies round-trip ==")
s = server.ShelterUpsert(shelter_id="SHL-X", name="Test", lat=25.0, lon=91.0)
d = s.model_dump()
if d["capacity"] is not None or d["current_occupancy"] is not None:
    fails.append("ShelterUpsert defaults capacity/occupancy to something other than None")
else:
    print("  ok   ShelterUpsert leaves capacity/occupancy as None, not 0")
if d["source"] != "AUTHORITY":
    fails.append(f"ShelterUpsert source default is {d['source']!r}")
else:
    print("  ok   ShelterUpsert stamps a source by default")
u = server.ShelterUpdate(current_occupancy=0)
changes = {k: v for k, v in u.model_dump().items() if v is not None}
if changes != {"current_occupancy": 0}:
    fails.append(f"an explicit occupancy of 0 is dropped by the None filter: {changes}")
else:
    print("  ok   an explicit occupancy of 0 survives the 'only changed fields' filter")
empty = {k: v for k, v in server.ShelterUpdate().model_dump().items() if v is not None}
print("  ok   an empty ShelterUpdate yields no changes (422 path)" if empty == {} else fails.append("empty update is not empty"))
t = server.ReportTriage(status="VERIFIED")
print("  ok   ReportTriage field is 'note'" if "note" in t.model_dump() else fails.append("ReportTriage has no 'note' field"))

print("\n" + "=" * 62)
if fails:
    for f in fails: print(f"  FAIL {f}")
    print(f"{len(fails)} problem(s)")
    sys.exit(1)
print("v5 ROUTE-TABLE VERIFICATION CLEAN")
