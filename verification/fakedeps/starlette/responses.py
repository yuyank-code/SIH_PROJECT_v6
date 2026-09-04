class JSONResponse:
    def __init__(self, content=None, status_code=200, **k):
        self.content, self.status_code = content, status_code
class Response(JSONResponse): pass
class PlainTextResponse(JSONResponse): pass
