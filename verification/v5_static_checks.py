#!/usr/bin/env python3
"""Static verification for the v5 frontend/backend seam.

Three things npm would normally catch and cannot here:
  1. an imported symbol that is never used (dead import, CRA build warning)
  2. a phosphor icon name that does not exist in the installed version
     (module-level crash at runtime, blank page, no build error)
  3. an api.get/post/patch path with no matching backend route (404 at runtime)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Works from either layout: beside the project tree during development, or
# inside it (verification/) as shipped in the zip.
_CANDIDATES = [os.path.join(HERE, ".."),
               os.path.join(HERE, "ner-slide-v4/SIH_project-main"),
               os.path.join(HERE, "SIH_project-main")]
ROOT = next((os.path.abspath(c) for c in _CANDIDATES
             if os.path.isdir(os.path.join(c, "backend", "app"))), None)
if ROOT is None:
    sys.exit("cannot locate the project root relative to this script")
FE = os.path.join(ROOT, "frontend/src")
SERVER = os.path.join(ROOT, "backend/server.py")

# The v3 baseline tree is a development convenience for diffing, not part of the
# shipped package. When it is absent the suite widens to every frontend file
# instead of the changed ones, and says so — a check that quietly passes because
# its input went missing is worse than one that fails.
_BASES = [os.path.join(HERE, "..", "..", "..", "SIH_project-main/frontend/src"),
          os.path.join(HERE, "SIH_project-main/frontend/src")]
BASE_FE = next((os.path.abspath(b) for b in _BASES if os.path.isdir(b)), None)

FAILS = []
def fail(msg):
    FAILS.append(msg)
    print(f"  FAIL {msg}")

def ok(msg):
    print(f"  ok   {msg}")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def changed_files():
    out = []
    for dirpath, _, names in os.walk(FE):
        for n in names:
            if not n.endswith((".js", ".jsx")):
                continue
            new = os.path.join(dirpath, n)
            if BASE_FE is None:
                out.append(new)
                continue
            old = new.replace(FE, BASE_FE, 1)
            if not os.path.exists(old) or read(old) != read(new):
                out.append(new)
    return sorted(out)


TARGETS = changed_files()
if BASE_FE is None:
    print(f"no v3 baseline tree found -- widening to all {len(TARGETS)} frontend files\n")
else:
    print(f"verifying {len(TARGETS)} changed/new frontend files\n")

# --------------------------------------------------------------------------
# 1. Icon names must already exist somewhere in the untouched baseline. npm is
#    unavailable, so the only evidence a name is valid in this exact phosphor
#    version is that the pre-existing app already imported it and built.
# --------------------------------------------------------------------------
print("== phosphor icon names exist in the installed version ==")
known = set()
for dirpath, _, names in os.walk(BASE_FE or FE):
    for n in names:
        if n.endswith((".js", ".jsx")):
            for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*[\"']@phosphor-icons/react[\"']", read(os.path.join(dirpath, n))):
                known |= {s.strip() for s in m.group(1).split(",") if s.strip()}

for path in TARGETS:
    src = read(path)
    for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*[\"']@phosphor-icons/react[\"']", src):
        for icon in (s.strip() for s in m.group(1).split(",") if s.strip()):
            if icon not in known:
                fail(f"{os.path.basename(path)}: icon '{icon}' is not attested anywhere in the baseline build")
if BASE_FE is None:
    print("  SKIP no v3 baseline to attest icon names against -- this check needs one, "
          "and cannot be satisfied by the files it is meant to be checking")
elif not FAILS:
    ok(f"every icon used is drawn from the {len(known)} names the baseline already builds with")

# --------------------------------------------------------------------------
# 2. Unused imports.
# --------------------------------------------------------------------------
print("\n== no dead imports ==")
before = len(FAILS)
IMPORT_RE = re.compile(r"^import\s+(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from\s*[\"'][^\"']+[\"'];?", re.M)
for path in TARGETS:
    src = read(path)
    body = IMPORT_RE.sub("", src)
    for m in IMPORT_RE.finditer(src):
        names = []
        if m.group(1):
            names.append(m.group(1))
        if m.group(2):
            for part in m.group(2).split(","):
                part = part.strip()
                if not part:
                    continue
                names.append(part.split(" as ")[-1].strip())
        for name in names:
            if not re.search(rf"\b{re.escape(name)}\b", body):
                fail(f"{os.path.basename(path)}: imports '{name}' but never uses it")
if len(FAILS) == before:
    ok("every import in every changed file is referenced")

# --------------------------------------------------------------------------
# 3. Frontend api.* paths must resolve to a registered backend route.
# --------------------------------------------------------------------------
print("\n== every frontend api call resolves to a backend route ==")
server = read(SERVER)
routes = {}
for m in re.finditer(r"@api\.(get|post|patch|put|delete)\(\s*[\"']([^\"']+)[\"']", server):
    routes.setdefault(m.group(1).upper(), set()).add(m.group(2))

def matches(method, path):
    for tmpl in routes.get(method, ()):
        t = re.escape(tmpl)
        t = re.sub(r"\\\{[^}]*\\\}", r"[^/]+", t)
        if re.fullmatch(t, path):
            return True
    return False

CALL_RE = re.compile(r"\bapi\.(get|post|patch|put|delete)\(\s*[`\"']([^`\"']*)")
seen = set()
before = len(FAILS)
for path in TARGETS:
    for m in CALL_RE.finditer(read(path)):
        method, raw = m.group(1).upper(), m.group(2)
        # `/reports/${id}/media` -> /reports/X/media ; drop a trailing partial
        norm = re.sub(r"\$\{[^}]*\}", "X", raw)
        norm = norm.split("?", 1)[0]  # query string is not part of the route path
        if "$" in raw and raw.endswith("/"):
            continue
        key = (method, norm, os.path.basename(path))
        if key in seen:
            continue
        seen.add(key)
        # RiskMap builds its path from a `prefix` variable; expand both modes.
        candidates = [norm]
        if norm.startswith("X"):
            candidates = ["/gis" + norm[1:], "/public/gis" + norm[1:]]
        if all(not matches(method, c) for c in candidates):
            fail(f"{os.path.basename(path)}: {method} {raw} -> no matching route ({candidates})")
        else:
            print(f"  ok   {method:6} {norm:34} <- {os.path.basename(path)}")
if len(FAILS) == before:
    ok("all resolved")

# --------------------------------------------------------------------------
# 4. Public (unauthenticated) reachability of the citizen-facing reads.
# --------------------------------------------------------------------------
print("\n== citizen reads are reachable without a bearer token ==")
mw = read(f"{ROOT}/backend/app/auth_middleware.py")
pub_prefix = "/api/public/" in mw
for p in ("/public/safe-route", "/public/shelters", "/public/gis/shelters"):
    if p in routes.get("GET", ()):
        ok(f"GET {p} registered")
    else:
        fail(f"GET {p} is not registered")
if pub_prefix:
    ok("auth middleware exempts the /api/public/ prefix, so those need no login")
else:
    fail("auth middleware does not exempt /api/public/")

# --------------------------------------------------------------------------
# 5. Write paths must stay role-gated; server secrets must stay server-side.
# --------------------------------------------------------------------------
print("\n== writes stay gated, secrets stay server-side ==")
for sig, role in [("async def create_shelter", "AUTHORITY"),
                  ("async def patch_shelter", "FIELD_OFFICER"),
                  ("async def triage_report", "FIELD_OFFICER")]:
    i = server.find(sig)
    if i < 0:
        fail(f"{sig} not found")
        continue
    head = server[max(0, i - 400):i + 400]
    if f'require_roles("{role}")' in head:
        ok(f"{sig.split()[-1]} requires {role}")
    else:
        fail(f"{sig.split()[-1]} is not gated on {role}")

secrets = ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "FIREBASE_SERVICE_ACCOUNT_JSON")
leaks = []
for dirpath, _, names in os.walk(FE):
    for n in names:
        src = read(os.path.join(dirpath, n))
        for s in secrets:
            if s in src:
                leaks.append(f"{n}:{s}")
if leaks:
    fail(f"server-only secrets referenced in frontend: {leaks}")
else:
    ok("no server-only secret name appears anywhere under frontend/src")

# --------------------------------------------------------------------------
# 6. No fabricated data: every new record/payload shape carries a source.
# --------------------------------------------------------------------------
print("\n== no fabricated data: source fields present ==")
sr = read(f"{ROOT}/backend/app/services/safe_route_service.py")
cs = read(f"{ROOT}/backend/app/services/citizen_service.py")
for label, src, needle in [("safe_route_service", sr, '"source"'),
                           ("citizen_service", cs, '"source"')]:
    ok(f"{label} tags its payloads with source") if needle in src else fail(f"{label} has no source field")
seed = read(f"{ROOT}/backend/app/data/ner_seed.py")
ok('shelter seed is tagged SEED_DEMO') if '"SEED_DEMO"' in seed else fail("shelter seed is not tagged")
mig = read(f"{ROOT}/backend/app/db/migration_seed.py")
if 'or 0' in mig or ", 0)" in mig.split("NER_SHELTERS")[-1]:
    fail("migration coerces a missing count to 0 somewhere in the shelter upsert")
else:
    ok("shelter migration writes capacity/occupancy through as-is, including None")

# --------------------------------------------------------------------------
print("\n" + "=" * 62)
if FAILS:
    print(f"{len(FAILS)} problem(s) found")
    sys.exit(1)
print("v5 STATIC VERIFICATION CLEAN")
