from datetime import datetime, timezone
from urllib.request import Request

import pytest

from app.seed_demo import APIError, EMAIL, WORKSPACE, NoRedirect, credentials, local_url, seed


@pytest.mark.parametrize("url", ["https://example.com", "http://example.com", "http://192.168.1.1:8000", "http://127.0.0.1:8000/path",
                                  "http://user:pass@127.0.0.1", "http://127.0.0.1?q=demo", "http://127.0.0.1#demo"])
def test_demo_rejects_nonlocal_or_ambiguous_targets(url):
    with pytest.raises(ValueError):
        local_url(url)


def test_demo_credentials_are_random_persistent_and_never_reset(tmp_path):
    path = tmp_path / "demo.json"
    first = credentials(path)
    assert first["email"] == EMAIL and len(first["password"]) >= 20
    assert credentials(path) == first
    assert credentials(tmp_path / "other.json")["password"] != first["password"]
    assert local_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    with pytest.raises(ValueError, match="redirects"):
        NoRedirect().redirect_request(Request("http://127.0.0.1"), None, 302, "", {}, "https://example.com")


class FakeAPI:
    def __init__(self):
        self.spaces = []
        self.rows = {}
        self.calls = []
        self.registered = False

    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path == "/auth/register":
            if self.registered:
                raise APIError(409)
            self.registered = True
            return {"id": "demo-user", "email": EMAIL}
        if path == "/auth/login":
            return {"id": "demo-user", "email": EMAIL}
        if path == "/workspaces":
            if method == "GET":
                return self.spaces
            self.spaces.append({"id": "demo-workspace", "name": data["name"], "role": "OWNER"})
            return self.spaces[0]
        assert path.startswith("/workspaces/demo-workspace/")
        suffix = path.split("/workspaces/demo-workspace", 1)[1].split("?", 1)[0]
        if method == "GET" and suffix == "/pipelines":
            return [{"id": "p1", "stages": [{"id": f"s{i}", "position": i} for i in range(4)]}]
        if method == "GET" and suffix == "/project-stages":
            return [{"id": "ps1"}]
        if method == "GET" and suffix == "/task-statuses":
            return [{"id": "ts1"}, {"id": "ts2"}]
        if method == "GET":
            return self.rows.setdefault(suffix, [])
        if suffix.count("/") == 1 and method == "POST":
            rows = self.rows.setdefault(suffix, [])
            row = {**data, "id": f"{suffix[1:]}-{len(rows)}"}
            rows.append(row)
            return row
        # Mutations below collection level belong only to freshly created demo objects.
        assert method in ("POST", "PUT", "PATCH")
        return {}


def test_demo_rerun_creates_no_duplicates_and_does_not_overwrite_user_edits():
    api = FakeAPI()
    state = {"email": EMAIL, "password": "demo-password-not-a-real-secret", "entities": {}}
    persisted = []
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    result = seed(api, state, lambda: persisted.append(True), now)
    assert result["deals"] == 12 and result["tasks"] == 9 and result["invoices"] == 4
    assert result["workspace"] == WORKSPACE and persisted
    api.rows["/deals"][0]["title"] = "An edited demo deal"
    api.calls.clear()
    seed(api, state, lambda: persisted.append(True), now)
    assert all(method == "GET" or path.startswith("/auth/") for method, path, _ in api.calls)
    assert api.rows["/deals"][0]["title"] == "An edited demo deal"
    assert len(api.rows["/deals"]) == 12
    assert not any("webhook" in path or "integration" in path for _, path, _ in api.calls)


def test_demo_refuses_untracked_workspaces_or_deleted_demo_records():
    api = FakeAPI()
    api.spaces = [{"id": "existing", "name": "Existing data", "role": "OWNER"}]
    state = {"email": EMAIL, "password": "demo-password-not-a-real-secret"}
    with pytest.raises(ValueError, match="untracked"):
        seed(api, state, lambda: None)
    assert not any(path.startswith("/workspaces/") or (method == "POST" and path == "/workspaces") for method, path, _ in api.calls)
    api = FakeAPI()
    seed(api, state, lambda: None)
    api.rows["/deals"].pop(0)
    api.calls.clear()
    with pytest.raises(ValueError, match="removed"):
        seed(api, state, lambda: None)
    assert all(method == "GET" or path.startswith("/auth/") for method, path, _ in api.calls)
