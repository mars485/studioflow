import {expect, test} from '@playwright/test';

test('explicit company merge preserves related objects and historical profiles across reload', async ({page}) => {
  await page.goto('/');
  const data = await page.evaluate(async () => {
    const post = async (path: string, body: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(body)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const get = async (path: string) => {
      const response = await fetch(`/api/v1${path}`);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    await post('/auth/register', {email: `company-merge-${Date.now()}-${Math.random()}@example.com`, password: 'Company-Merge-E2E-password123', first_name: 'Merger E2E'});
    const workspace = await post('/workspaces', {name: 'Слияние компаний E2E'});
    const base = `/workspaces/${workspace.id}`;
    const target = await post(base + '/clients', {name: 'Основная компания слияния', email: 'merge@example.com'});
    const source = await post(base + '/clients', {name: 'Дублирующая компания слияния', email: 'merge@example.com', phone: '+7 900 111 22 33', notes: 'Исходное описание для истории'});
    const contact = await post(base + '/contacts', {first_name: 'Контакт слияния', client_ids: [source.id, target.id]});
    const pipelines = await get(base + '/pipelines');
    const deal = await post(base + '/deals', {title: 'Сделка слияния E2E', client_id: source.id, pipeline_id: pipelines[0].id, stage_id: pipelines[0].stages[0].id, amount: '1000.25'});
    const project = await post(base + '/projects', {title: 'Проект слияния E2E', client_id: source.id});
    const organization = await post(base + '/organizations', {name: 'Учебный продавец слияния'});
    const invoice = await post(base + '/invoices', {client_id: source.id, organization_id: organization.id,
      issued_on: '2026-10-26', amount: '1000.25', description: 'Учебная услуга', deal_id: deal.id, project_id: project.id});
    return {base, sourceId: source.id, targetId: target.id, contactId: contact.id, dealId: deal.id, projectId: project.id, invoiceId: invoice.id, buyer: invoice.buyer};
  });
  await page.reload();
  await page.getByRole('button', {name: 'Клиенты', exact: true}).click();
  await page.getByRole('button', {name: 'Проверить дубли: Основная компания слияния', exact: true}).click();
  await page.getByRole('button', {name: 'Слияние: Дублирующая компания слияния', exact: true}).click();
  const merge = page.getByRole('region', {name: 'Слияние компаний', exact: true});
  await expect(merge.getByText('Останется: Основная компания слияния', {exact: true})).toBeVisible();
  const submit = merge.getByRole('button', {name: 'Подтвердить слияние', exact: true});
  await expect(submit).toBeDisabled();
  await page.setViewportSize({width: 390, height: 844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await merge.getByRole('checkbox', {name: 'Взять из исходной: Телефон', exact: true}).check();
  await merge.getByRole('checkbox', {name: /Я проверил компании/}).check();
  await submit.click();
  await expect(merge.getByRole('status')).toContainText('Компании объединены');
  await expect(page.getByRole('button', {name: 'Дублирующая компания слияния', exact: true})).toHaveCount(0);
  const persisted = await page.evaluate(async ({base, sourceId, targetId, contactId, dealId, projectId, invoiceId}) => {
    const source = await fetch(`/api/v1${base}/clients/${sourceId}`);
    const paths = [`/clients/${targetId}`, `/contacts/${contactId}`, `/deals/${dealId}`, `/projects/${projectId}`, `/invoices/${invoiceId}`];
    const rows = await Promise.all(paths.map(async path => (await fetch(`/api/v1${base}${path}`)).json()));
    return {sourceStatus: source.status, rows};
  }, data);
  expect(persisted.sourceStatus).toBe(404);
  expect(persisted.rows[0].phone).toBe('+7 900 111 22 33');
  expect(persisted.rows[1].client_ids).toEqual([data.targetId]);
  for (const index of [2, 3, 4]) expect(persisted.rows[index].client_id).toBe(data.targetId);
  expect(persisted.rows[4].buyer).toEqual(data.buyer);
  await page.reload();
  await page.getByRole('button', {name: 'Клиенты', exact: true}).click();
  await page.getByRole('button', {name: 'Основная компания слияния', exact: true}).click();
  const company = page.getByRole('dialog', {name: 'Компании', exact: true});
  await company.getByRole('button', {name: 'История слияний', exact: true}).click();
  await company.getByText(/Квитанция слияния:/).click();
  await expect(company.getByText('Исходное описание для истории', {exact: true})).toBeVisible();
  await expect(company.getByText(/Merger E2E/)).toBeVisible();
});
