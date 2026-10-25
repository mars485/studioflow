import {expect, test} from '@playwright/test';

test('audit retains core deal operations after deletion and reload', async ({page}) => {
  await page.goto('/');
  const target = await page.evaluate(async () => {
    const call = async (path: string, method: string, body?: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method, headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'},
        body: body === undefined ? undefined : JSON.stringify(body)});
      if (!response.ok) throw new Error(await response.text());
      return response.status === 204 ? null : response.json();
    };
    await call('/auth/register', 'POST', {email: `audit-${Date.now()}-${Math.random()}@example.com`, password: 'Audit-E2E-password123', first_name: 'Audit E2E'});
    const space = await call('/workspaces', 'POST', {name: 'Аудит E2E'});
    const base = `/workspaces/${space.id}`;
    const client = await call(`${base}/clients`, 'POST', {name: 'Клиент аудита'});
    const pipelines = await call(`${base}/pipelines`, 'GET');
    const deal = await call(`${base}/deals`, 'POST', {title: 'Private audit title', client_id: client.id,
      pipeline_id: pipelines[0].id, stage_id: pipelines[0].stages[0].id});
    await call(`${base}/deals/${deal.id}`, 'PATCH', {title: 'Private changed title'});
    await call(`${base}/deals/${deal.id}`, 'PATCH', {title: 'Private changed title'});
    await call(`${base}/deals/${deal.id}`, 'DELETE');
    return {workspaceId: space.id, dealId: deal.id};
  });
  for (let pass = 0; pass < 2; pass++) {
    await page.reload();
    await page.getByRole('button', {name: 'Настройки', exact: true}).click();
    await page.getByLabel('Студия в настройках').selectOption(target.workspaceId);
    await page.getByRole('button', {name: 'Открыть аудит сделок'}).click();
    const audit = page.getByRole('region', {name: 'Аудит сделок', exact: true});
    await expect(audit.getByText('Записей аудита: 3', {exact: true})).toBeVisible();
    await expect(audit.getByText('Изменены поля: title', {exact: true})).toBeVisible();
    await expect(audit.getByText(/Сделка:/)).toHaveCount(3);
    await expect(audit.getByText(/Private/)).toHaveCount(0);
    await audit.getByLabel('UUID сделки в аудите').fill(target.dealId);
    await audit.getByLabel('Операция аудита', {exact: true}).selectOption('DELETED');
    await audit.getByRole('button', {name: 'Применить фильтр аудита'}).click();
    await expect(audit.getByText('Записей аудита: 1', {exact: true})).toBeVisible();
  }
});
