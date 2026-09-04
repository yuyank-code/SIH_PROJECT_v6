"""Minimal fastapi stand-in: records route registrations so the real server.py
can be imported and its route table inspected without the real package."""
class HTTPException(Exception):
    def __init__(self, status_code=500, detail=None):
        self.status_code, self.detail = status_code, detail
        super().__init__(f"{status_code}:{detail}")

class Request:  pass
class Response: pass
class BackgroundTasks: pass
class UploadFile: pass
def File(*a, **k): return None
def Form(*a, **k): return None
def Query(default=None, **k): return default
def Body(default=None, **k): return default
def Header(default=None, **k): return default
def Depends(dep=None): return ("Depends", dep)

class APIRouter:
    def __init__(self, *a, **k):
        self.prefix = k.get("prefix", "")
        self.registered = []
    def _reg(self, method, path, **k):
        def deco(fn):
            self.registered.append((method, self.prefix + path, fn, k))
            return fn
        return deco
    def get(self, p, **k): return self._reg("GET", p, **k)
    def post(self, p, **k): return self._reg("POST", p, **k)
    def patch(self, p, **k): return self._reg("PATCH", p, **k)
    def put(self, p, **k): return self._reg("PUT", p, **k)
    def delete(self, p, **k): return self._reg("DELETE", p, **k)
    def include_router(self, r, **k): self.registered += r.registered
    def on_event(self, name):
        def deco(fn): return fn
        return deco

class FastAPI(APIRouter):
    def add_middleware(self, *a, **k): pass
    def middleware(self, kind):
        def deco(fn): return fn
        return deco
    def mount(self, *a, **k): pass
    def exception_handler(self, *a, **k):
        def deco(fn): return fn
        return deco
