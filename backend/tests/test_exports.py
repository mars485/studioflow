import csv
import io
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.models import WorkspaceMember
from app.api.v1.exports import export_csv, safe_cell
from fastapi import HTTPException
from types import SimpleNamespace

pytestmark = pytest.mark.asyncio


async def test_export_csv_quotes_unicode_formulas_and_workspace_roles(crm):
    http, base, db = crm['http'], crm['base'], crm['db']
    title = '=HYPERLINK("https://invalid.example";"тест")'
    created = await http.post(base + '/deals', json={**crm['payload'], 'title': title})
    assert created.status_code == 201
    result = await http.get(base + '/exports/deals.csv?pipeline_id=' + str(crm['pipelines'][0].id))
    assert result.status_code == 200, result.text
    assert result.content.startswith(b'\xef\xbb\xbf')
    assert result.headers['content-disposition'] == 'attachment; filename="studioflow-deals.csv"'
    assert result.headers['x-content-type-options'] == 'nosniff'
    rows = list(csv.DictReader(io.StringIO(result.content.decode('utf-8-sig')), delimiter=';'))
    assert len(rows) == 1 and rows[0]['id'] == created.json()['id']
    assert rows[0]['title'] == "'" + title and rows[0]['amount'] == '65000.25'
    foreign = base.replace(str(crm['spaces'][0].id), str(crm['spaces'][1].id))
    assert (await http.get(foreign + '/exports/deals.csv')).status_code == 404
    assert (await http.get(base + '/exports/deals.csv?pipeline_id=' + str(uuid4()))).status_code == 404
    for entity in ('clients', 'contacts'):
        assert (await http.get(base + '/exports/' + entity + '.csv')).status_code == 200
    member = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == crm['spaces'][0].id))
    member.role = 'MANAGER'; await db.commit()
    for entity in ('deals', 'clients', 'contacts'):
        assert (await http.get(base + '/exports/' + entity + '.csv')).status_code == 403


async def test_formula_prefixes_and_plain_csv_values():
    for value in ('=1+1', '+123', '-1', '@SUM(1)', '  =1', '\ufeff=1', '\tformula', '\rrow', '\nrow'):
        assert safe_cell(value) == "'" + value
    for value in ('ООО "Клиент"; тест', 'hello', '100.00', ''):
        assert safe_cell(value) == value
    assert safe_cell(None) == ''


async def test_export_refuses_over_limit_instead_of_silent_truncation():
    class FakeDB:
        async def execute(self, query):
            assert query._limit_clause.value == 5001
            return SimpleNamespace(all=lambda: [()] * 5001)
    with pytest.raises(HTTPException) as error:
        await export_csv('clients', None, uuid4(), FakeDB())
    assert error.value.status_code == 413
