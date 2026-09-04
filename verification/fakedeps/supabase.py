"""Stub supabase-py. Queries return empty result sets so route bodies can be
introspected; nothing here invents rows."""
class _Result:
    def __init__(self, data=None): self.data = data if data is not None else []
class _Q:
    def __getattr__(self, name): return lambda *a, **k: self
    def execute(self): return _Result()
    async def aexecute(self): return _Result()
class _Storage:
    def from_(self, *a, **k): return _Q()
    def get_bucket(self, *a, **k): return _Q()
class _Auth:
    def __getattr__(self, name): return lambda *a, **k: _Result()
class AsyncClient:
    def table(self, *a, **k): return _Q()
    def rpc(self, *a, **k): return _Q()
    def from_(self, *a, **k): return _Q()
    @property
    def storage(self): return _Storage()
    @property
    def auth(self): return _Auth()
class Client(AsyncClient): pass
class AClient(AsyncClient): pass
async def acreate_client(*a, **k): return AsyncClient()
def create_client(*a, **k): return Client()
class AsyncClientOptions:
    def __init__(self, *a, **k): pass
class ClientOptions(AsyncClientOptions): pass
