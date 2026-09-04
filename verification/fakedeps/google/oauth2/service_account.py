class Credentials:
    token = "stub-token"
    @classmethod
    def from_service_account_info(cls, *a, **k): return cls()
    @classmethod
    def from_service_account_file(cls, *a, **k): return cls()
    def with_scopes(self, *a, **k): return self
    def refresh(self, *a, **k): pass
