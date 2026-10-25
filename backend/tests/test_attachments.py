import hashlib
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import WorkspaceMember
from app.models.entities import DealAttachmentContent

pytestmark = pytest.mark.asyncio


async def paths(crm):
    deal = (await crm["http"].post(crm["base"] + "/deals", json=crm["payload"])).json()
    return crm["base"] + "/deals/" + deal["id"] + "/attachments"


def upload_path(path, name="бриф.txt", key=None):
    return path + f"/upload?filename={quote(name, safe='')}&upload_key={key or uuid4()}"


async def test_attachment_upload_download_legacy_and_cascade(crm):
    http, path = crm["http"], await paths(crm)
    legacy = await http.post(path, json={"filename": "old.pdf", "size_bytes": 2048})
    assert legacy.status_code == 201 and legacy.json()["has_content"] is False
    assert (await http.get(path + "/" + legacy.json()["id"] + "/download")).status_code == 404
    data = "Бриф клиента\n".encode() + bytes(range(256))
    result = await http.post(upload_path(path), content=data, headers={"Content-Type": "text/plain"})
    assert result.status_code == 201, result.text
    attachment = result.json()
    assert attachment["size_bytes"] == len(data) and attachment["has_content"]
    assert attachment["sha256"] == hashlib.sha256(data).hexdigest()
    downloaded = await http.get(path + "/" + attachment["id"] + "/download")
    assert downloaded.status_code == 200 and downloaded.content == data
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["content-security-policy"] == "sandbox"
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''" in downloaded.headers["content-disposition"]
    assert len((await http.get(path)).json()) == 2
    assert (await http.delete(path + "/" + attachment["id"])).status_code == 204
    assert await crm["db"].get(DealAttachmentContent, UUID(attachment["id"])) is None
    assert (await http.get(path + "/" + attachment["id"] + "/download")).status_code == 404
    # Cascading deal deletion removes binary storage, not just the visible metadata.
    again = (await http.post(upload_path(path), content=data)).json()
    assert (await http.delete(path.removesuffix("/attachments"))).status_code == 204
    assert await crm["db"].get(DealAttachmentContent, UUID(again["id"])) is None


async def test_upload_limits_actual_stream_quota_and_idempotency(crm, monkeypatch):
    http, path = crm["http"], await paths(crm)
    monkeypatch.setattr(settings, "attachment_max_bytes", 8)
    monkeypatch.setattr(settings, "attachment_workspace_quota_bytes", 10)
    assert (await http.post(upload_path(path), content=b"123456789")).status_code == 413

    async def stream():
        yield b"12345"
        yield b"6789"

    assert (await http.post(upload_path(path), content=stream())).status_code == 413
    key = uuid4()
    url = upload_path(path, key=key)
    first = await http.post(url, content=b"12345678")
    assert first.status_code == 201, first.text
    assert (await http.post(url, content=b"12345678")).json()["id"] == first.json()["id"]
    assert (await http.post(url, content=b"different")).status_code == 413  # size checked before replay
    assert (await http.post(url, content=b"12345679")).status_code == 409
    other = await paths(crm)
    assert (await http.post(upload_path(other), content=b"123")).status_code == 413
    assert (await http.post(upload_path(other), content=b"12")).status_code == 201
    assert (await http.delete(path + "/" + first.json()["id"])).status_code == 204
    assert (await http.post(upload_path(other), content=b"12345678")).status_code == 201


async def test_attachment_scopes_membership_and_csrf(crm):
    http, path = crm["http"], await paths(crm)
    row = (await http.post(upload_path(path), content=b"private bytes")).json()
    suffix = "/" + row["id"] + "/download"
    other_deal = await paths(crm)
    assert (await http.get(other_deal + suffix)).status_code == 404
    crm["db"].add(WorkspaceMember(workspace_id=crm["spaces"][1].id, user_id=crm["user"].id))
    await crm["db"].commit()
    foreign = path.replace(str(crm["spaces"][0].id), str(crm["spaces"][1].id))
    assert (await http.get(foreign + suffix)).status_code == 404
    assert (await http.post(upload_path(foreign), content=b"bad")).status_code == 404
    assert (await http.delete(foreign + "/" + row["id"])).status_code == 404
    assert (await http.post(upload_path(path), content=b"bad", headers={"X-StudioFlow-Request": "0"})).status_code == 403
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    await crm["db"].delete(member)
    await crm["db"].commit()
    assert (await http.get(path + suffix)).status_code == 404
    assert (await http.post(upload_path(path), content=b"bad")).status_code == 404


async def test_attachment_names_empty_files_and_active_content_forced_download(crm):
    http, path = crm["http"], await paths(crm)
    for name in ("../file", "C:\\file.txt", "\r\nheader", "..", "  ", "evil\u202eexe.txt"):
        assert (await http.post(upload_path(path, name), content=b"x")).status_code == 422
    empty = await http.post(upload_path(path, "empty.txt"), content=b"")
    assert empty.status_code == 201 and empty.json()["has_content"]
    active = await http.post(upload_path(path, "example.html"), content=b"<script>alert(1)</script>", headers={"Content-Type": "text/html"})
    download = await http.get(path + "/" + active.json()["id"] + "/download")
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["content-disposition"].startswith("attachment;")
