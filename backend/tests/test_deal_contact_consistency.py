import pytest

pytestmark = pytest.mark.asyncio


async def test_legacy_primary_and_contact_links_stay_in_sync(crm):
    http, base = crm["http"], crm["base"]
    contacts = []
    for name in ("Анна", "Борис"):
        contacts.append((await http.post(base + "/contacts", json={"first_name": name, "client_ids": [str(crm["clients"][0].id)]})).json())
    deal = (await http.post(base + "/deals", json={**crm["payload"], "contact_id": contacts[0]["id"]})).json()
    path = base + "/deals/" + deal["id"]
    links = (await http.get(path + "/contacts")).json()
    assert len(links) == 1 and links[0]["contact_id"] == contacts[0]["id"] and links[0]["is_primary"]
    assert (await http.post(path + "/contacts", json={"contact_id": contacts[1]["id"]})).status_code == 201
    assert (await http.patch(path + "/contacts/" + contacts[1]["id"], json={"is_primary": True})).status_code == 200
    updated = (await http.get(path)).json()
    assert updated["contact_id"] == contacts[1]["id"] and updated["contact_name"] == "Борис"
    changed = await http.patch(path, json={"contact_id": contacts[0]["id"]})
    assert changed.status_code == 200
    links = (await http.get(path + "/contacts")).json()
    assert len(links) == 2 and [row["contact_id"] for row in links if row["is_primary"]] == [contacts[0]["id"]]
    cleared = await http.patch(path, json={"contact_id": None})
    assert cleared.status_code == 200 and cleared.json()["contact_id"] == contacts[1]["id"]
    assert (await http.delete(path + "/contacts/" + contacts[1]["id"])).status_code == 204
    final = (await http.get(path)).json()
    assert final["contact_id"] is None and final["contact_name"] is None
    assert (await http.get(path + "/contacts")).json() == []
    for contact in contacts:
        assert (await http.get(base + "/contacts/" + contact["id"])).status_code == 200


async def test_first_external_contact_becomes_primary_and_can_be_edited_without_company_relink(crm):
    http, base = crm["http"], crm["base"]
    deal = (await http.post(base + "/deals", json=crm["payload"])).json()
    contact = (await http.post(base + "/contacts", json={"first_name": "Внешний контакт"})).json()
    path = base + "/deals/" + deal["id"]
    added = await http.post(path + "/contacts", json={"contact_id": contact["id"]})
    assert added.status_code == 201 and added.json()["is_primary"]
    assert (await http.get(path)).json()["contact_id"] == contact["id"]
    # An existing explicit relation is enough to preserve it while editing the deal.
    assert (await http.patch(path, json={"description": "Обновлённое описание"})).status_code == 200
    assert (await http.patch(path, json={"contact_id": contact["id"]})).status_code == 200
    assert (await http.patch(path + "/contacts/" + contact["id"], json={"is_primary": False})).status_code == 409
    assert (await http.delete(path + "/contacts/" + contact["id"])).status_code == 204
    # Once explicitly detached, the old form cannot silently assign an unrelated contact.
    assert (await http.patch(path, json={"contact_id": contact["id"]})).status_code == 422
