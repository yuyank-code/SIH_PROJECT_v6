class HTTPError(Exception): pass
class HTTPStatusError(HTTPError): pass
class RequestError(HTTPError): pass
class TimeoutException(HTTPError): pass
class Timeout:
    def __init__(self, *a, **k): pass
class Limits:
    def __init__(self, *a, **k): pass
class Response:
    status_code = 200
    def json(self): return {}
    def raise_for_status(self): pass
    @property
    def text(self): return ""
class AsyncClient:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def get(self, *a, **k): raise RequestError("stub httpx: no network in harness")
    async def post(self, *a, **k): raise RequestError("stub httpx: no network in harness")
    async def aclose(self): pass
class Client(AsyncClient): pass
