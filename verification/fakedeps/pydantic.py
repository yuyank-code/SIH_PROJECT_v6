"""Minimal pydantic v2 stand-in. Enough to declare models and round-trip
model_dump(), which is all server.py's request bodies actually rely on here."""
import typing
_UNSET = object()

def Field(default=_UNSET, **k):
    return default if default is not _UNSET else None

class _Meta(type):
    def __new__(mcls, name, bases, ns):
        cls = super().__new__(mcls, name, bases, ns)
        fields = {}
        for b in bases:
            fields.update(getattr(b, "__fields_map__", {}))
        for fname, ftype in ns.get("__annotations__", {}).items():
            fields[fname] = ns.get(fname, _UNSET)
        cls.__fields_map__ = fields
        return cls

class BaseModel(metaclass=_Meta):
    def __init__(self, **data):
        for f, default in self.__fields_map__.items():
            if f in data:
                setattr(self, f, data[f])
            elif default is not _UNSET:
                setattr(self, f, default)
            else:
                raise TypeError(f"missing required field {f!r}")
        unknown = set(data) - set(self.__fields_map__)
        if unknown:
            raise TypeError(f"unexpected fields {unknown}")
    def model_dump(self, **k):
        out = {f: getattr(self, f, None) for f in self.__fields_map__}
        if k.get("exclude_none"):
            out = {a: b for a, b in out.items() if b is not None}
        return out
    dict = model_dump

def field_validator(*a, **k):
    def deco(fn): return fn
    return deco
def model_validator(*a, **k):
    def deco(fn): return fn
    return deco
class ValidationError(Exception): pass
class ConfigDict(dict): pass
