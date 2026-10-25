from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.models import Deal, WorkspaceMember

pytestmark = pytest.mark.asyncio


async def test_analytics_empty_counts_stage_changes_roles_and_scope(crm):
    http, base = crm['http'], crm['base']
    empty = await http.get(base + '/analytics')
    assert empty.status_code == 200, empty.text
    assert empty.json()['counts'] == {'OPEN': 0, 'WON': 0, 'LOST': 0}
    assert empty.json()['conversion_percent'] is None and empty.json()['stages'] == []
    pipelines = (await http.get(base + '/pipelines')).json()
    stage_path = base + '/pipelines/' + pipelines[0]['id'] + '/stages'
    won_response = await http.post(stage_path, json={'name': 'Успешно', 'stage_type': 'WON'})
    lost_response = await http.post(stage_path, json={'name': 'Отказ', 'stage_type': 'LOST'})
    assert won_response.status_code == 201 and lost_response.status_code == 201
    won, lost = won_response.json(), lost_response.json()
    deals = []
    for index in range(3):
        response = await http.post(base + '/deals', json={**crm['payload'], 'amount': str(100 + index), 'responsible_user_id': str(crm['user'].id)})
        assert response.status_code == 201
        deals.append(response.json())
    assert (await http.patch(base + '/deals/' + deals[0]['id'], json={'stage_id': won['id']})).status_code == 200
    assert (await http.patch(base + '/deals/' + deals[1]['id'], json={'stage_id': lost['id']})).status_code == 200
    report = (await http.get(base + '/analytics')).json()
    assert report['counts'] == {'OPEN': 1, 'WON': 1, 'LOST': 1} and report['conversion_percent'] == 50.0
    assert sum(row['count'] for row in report['managers']) == 3
    assert report['work']['missing_followups'] == 1
    assert 'finance' not in report
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/analytics')).status_code == 404
    assert (await http.get(base + '/analytics?pipeline_id=' + str(uuid4()))).status_code == 404
    member = await crm['db'].scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await crm['db'].commit()
    assert (await http.get(base + '/analytics')).status_code == 200


async def test_analytics_local_date_cohort_currency_and_work_are_separate(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    workspace = crm['spaces'][0]
    workspace.timezone = 'Asia/Yekaterinburg'
    await db.commit()
    ids = []
    for _ in range(3):
        response = await http.post(base + '/deals', json=crm['payload'])
        assert response.status_code == 201
        ids.append(UUID(response.json()['id']))
    # October 24 local day is October 23 19:00Z through October 24 18:59:59Z.
    stamps = ['2026-10-23T18:59:59+00:00', '2026-10-23T19:00:00+00:00', '2026-10-24T18:59:59+00:00']
    for index, identity in enumerate(ids):
        row = await db.get(Deal, identity)
        row.created_at = datetime.fromisoformat(stamps[index])
        row.amount = 100
        row.currency = 'USD' if index == 2 else 'RUB'
    await db.commit()
    task = await http.post(base + '/tasks', json={'title': 'Просрочена', 'due_at': '2020-01-01T00:00:00Z'})
    assert task.status_code == 201
    report = await http.get(base + '/analytics?from_date=2026-10-24&to_date=2026-10-24')
    assert report.status_code == 200, report.text
    data = report.json()
    assert data['counts']['OPEN'] == 2
    assert {row['currency']: row['amount'] for row in data['stages']} == {'RUB': '100.00', 'USD': '100.00'}
    assert data['work']['active_tasks'] == 1 and data['work']['overdue_tasks'] == 1
    assert data['work']['missing_followups'] == 3
    assert (await http.get(base + '/analytics?from_date=2026-10-25&to_date=2026-10-24')).status_code == 422
    assert (await http.get(base + '/analytics?to_date=9999-12-31')).status_code == 422
