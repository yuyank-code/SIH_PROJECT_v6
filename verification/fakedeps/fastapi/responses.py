class JSONResponse:
    def __init__(self, content=None, status_code=200, **k):
        self.content, self.status_code = content, status_code
class PlainTextResponse(JSONResponse): pass
class StreamingResponse(JSONResponse): pass
class FileResponse(JSONResponse): pass
