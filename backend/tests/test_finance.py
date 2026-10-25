from uuid import uuid4

import pytest
from sqlalchemy import select
from app.models import WorkspaceMember

pytestmark = pytest.mark.asyncio


async def setup_invoice(crm, **overrides):
    http, base = crm["http"], crm["base"]
    organization = await http.post(base + "/organizations", json={"name": "Студия", "tax_id": "1234567890", "bank": "Банк"})
    assert organization.status_code == 201, organization.text
    payload = {"organization_id": organization.json()["id"], "client_id": str(crm["clients"][0].id),
               "amount": "100.25", "issued_on": "2026-10-24", "description": "Разработка сайта", **overrides}
    created = await http.post(base + "/invoices", json=payload)
    assert created.status_code == 201, created.text
    return created.json(), payload


async def test_invoice_payments_idempotency_and_acts(crm):
    http, base = crm["http"], crm["base"]
    invoice, _ = await setup_invoice(crm)
    path = base + "/invoices/" + invoice["id"]
    assert invoice["number"] == 1 and invoice["status"] == "DRAFT"
    assert invoice["paid_amount"] == "0.00"
    payment = {"request_key": str(uuid4()), "paid_on": "2026-10-24", "amount": "40.10"}
    assert (await http.post(path + "/payments", json=payment)).status_code == 409
    assert (await http.patch(path, json={"state": "ISSUED"})).status_code == 200
    assert (await http.post(path + "/sent")).json()["sent_at"] is not None
    first = await http.post(path + "/payments", json=payment)
    assert first.status_code == 201, first.text
    assert (await http.post(path + "/payments", json=payment)).json()["id"] == first.json()["id"]
    assert (await http.post(path + "/payments", json={**payment, "amount": "41"})).status_code == 409
    current = (await http.get(path)).json()
    assert current["status"] == "PARTIAL" and current["paid_amount"] == "40.10" and current["remaining_amount"] == "60.15"
    assert (await http.patch(path, json={"state": "CANCELLED"})).status_code == 409
    assert (await http.post(path + "/payments", json={**payment, "request_key": str(uuid4()), "amount": "60.16"})).status_code == 422
    assert (await http.post(path + "/payments", json={**payment, "request_key": str(uuid4()), "amount": "60.15"})).status_code == 201
    assert (await http.get(path)).json()["status"] == "PAID"
    assert len((await http.get(path + "/payments")).json()) == 2
    act = await http.post(path + "/acts", json={"issued_on": "2026-10-24"})
    assert act.status_code == 201 and act.json()["number"] == 1
    signed = (await http.post(base + "/acts/" + act.json()["id"] + "/sign")).json()
    assert signed["status"] == "SIGNED" and signed["signed_at"]
    assert (await http.get(path + "/acts")).json()[0]["status"] == "SIGNED"


async def test_finance_snapshots_numbering_links_and_validation(crm):
    http, base = crm["http"], crm["base"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    invoice, payload = await setup_invoice(crm, deal_id=deal["id"])
    path = base + "/invoices/" + invoice["id"]
    assert (await http.patch(path, json={"state": "CANCELLED"})).status_code == 200
    assert (await http.patch(path, json={"state": "ISSUED"})).status_code == 409
    second = (await http.post(base + "/invoices", json=payload)).json()
    assert second["number"] == 2
    assert (await http.put(base + "/organizations/" + payload["organization_id"], json={"name": "Другое название"})).status_code == 200
    assert (await http.get(path)).json()["seller"]["name"] == "Студия"
    assert (await http.delete(base + "/deals/" + deal["id"])).status_code == 204
    assert (await http.get(path)).json()["deal_id"] is None
    for amount in ("0", "-1", "1.001", "NaN", "1000000000000"):
        assert (await http.post(base + "/invoices", json={**payload, "deal_id": None, "amount": amount})).status_code == 422
    assert (await http.post(base + "/invoices", json={**payload, "client_id": str(crm["clients"][1].id)})).status_code == 404
    assert (await http.post(base + "/organizations", json={"name": "Компания", "tax_id": "bad"})).status_code == 422


async def test_finance_every_route_denies_manager_and_foreign_workspace(crm):
    http, base = crm["http"], crm["base"]
    invoice, payload = await setup_invoice(crm)
    other = f'/api/v1/workspaces/{crm["spaces"][1].id}'
    # Give access to the second workspace: object isolation is tested separately from membership.
    crm["db"].add(WorkspaceMember(workspace_id=crm["spaces"][1].id, user_id=crm["user"].id, role="OWNER"))
    await crm["db"].commit()
    assert (await http.get(other + "/invoices/" + invoice["id"])).status_code == 404
    assert (await http.get(other + "/invoices")).json() == []
    assert (await http.post(other + "/invoices", json=payload)).status_code == 404
    member = await crm["db"].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm["spaces"][0].id))
    member.role = "MANAGER"
    await crm["db"].commit()
    routes = [("GET", "/organizations", None), ("POST", "/organizations", {"name": "X"}),
              ("PUT", "/organizations/" + payload["organization_id"], {"name": "X"}),
              ("GET", "/invoices", None), ("POST", "/invoices", payload),
              ("GET", "/invoices/" + invoice["id"], None),
              ("PATCH", "/invoices/" + invoice["id"], {"state": "ISSUED"}),
              ("POST", "/invoices/" + invoice["id"] + "/sent", None),
              ("GET", "/invoices/" + invoice["id"] + "/payments", None),
              ("POST", "/invoices/" + invoice["id"] + "/payments", {"request_key": str(uuid4()), "paid_on": "2026-10-24", "amount": "1"}),
              ("GET", "/invoices/" + invoice["id"] + "/acts", None),
              ("POST", "/invoices/" + invoice["id"] + "/acts", {"issued_on": "2026-10-24"}),
              ("POST", "/acts/" + str(uuid4()) + "/sign", None)]
    for method, suffix, body in routes:
        response = await http.request(method, base + suffix, json=body)
        assert response.status_code == 403, (method, suffix, response.text)


async def test_invoice_project_deletion_keeps_receivable_and_client_is_protected(crm):
    http, base = crm["http"], crm["base"]
    project = await http.post(base + "/projects", json={"title": "Проект", "client_id": str(crm["clients"][0].id)})
    assert project.status_code == 201
    invoice, _ = await setup_invoice(crm, project_id=project.json()["id"])
    assert (await http.delete(base + "/projects/" + project.json()["id"])).status_code == 204
    kept = (await http.get(base + "/invoices/" + invoice["id"])).json()
    assert kept["project_id"] is None and kept["amount"] == "100.25"
    assert (await http.delete(base + "/clients/" + str(crm["clients"][0].id))).status_code == 409
