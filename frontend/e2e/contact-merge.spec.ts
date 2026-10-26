import {expect, test} from '@playwright/test';

test('contact merge preserves primary roles, shared relationships and historical profiles', async ({page}) => {
  await page.goto('/');
  const data = await page.evaluate(async () => {
    const post = async (path: string, body: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(body)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    await post('/auth/register', {email: `contact-merge-${Date.now()}-${Math.random()}@example.com`, password: 'Contact-Merge-E2E-password123', first_name: 'Contact Merger E2E'});
    const workspace = await post('/workspaces', {name: 'Слияние контактов E2E'});
    const base = `/workspaces/${workspace.id}`;
    const company = await post(base + '/clients', {name: 'Компания контактов E2E'});
    const source = await post(base + '/contacts', {first_name: 'Дубликат контакта E2E', email: 'person-merge@example.com', phone: '+7 900 333 44 55', notes: 'Исходная заметка контакта E2E', client_ids: [company.id]});
    const target = await post(base + '/contacts', {first_name: 'Основной контакт E2E', email: 'person-merge@example.com', client_ids: [company.id]});
    const third = await post(base + '/contacts', {first_name: 'Третий основной E2E', client_ids: [company.id]});
    const pipelines = await (await fetch(`/api/v1${base}/pipelines`)).json();
    const dealInput = {client_id: company.id, pipeline_id: pipelines[0].id, stage_id: pipelines[0].stages[0].id};
    const deal = await post(base + '/deals', {...dealInput, title: 'Основной контакт слияния E2E', contact_id: source.id});
    await post(base + '/deals/' + deal.id + '/contacts', {contact_id: target.id});
    const thirdDeal = await post(base + '/deals', {...dealInput, title: 'Третий контакт слияния E2E', contact_id: third.id});
    await post(base + '/deals/' + thirdDeal.id + '/contacts', {contact_id: source.id});
    const wonStage = pipelines[0].stages.find((stage: {stage_type: string}) => stage.stage_type === 'WON');
    const changed = await fetch(`/api/v1${base}/deals/${deal.id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify({stage_id: wonStage.id})});
    if (!changed.ok) throw new Error(await changed.text());
    const project = await post(base + '/projects', {title: 'Проект контактов E2E', deal_id: deal.id});
    const task = await post(base + '/tasks', {title: 'Задача контакта E2E', contact_id: source.id, deal_id: deal.id, project_id: project.id});
    return {base, sourceId: source.id, targetId: target.id, thirdId: third.id, dealId: deal.id, thirdDealId: thirdDeal.id, projectId: project.id, taskId: task.id};
  });
  await page.reload();
  await page.getByRole('button', {name: 'Клиенты', exact: true}).click();
  await page.getByRole('tab', {name: 'Контакты', exact: true}).click();
  await page.getByRole('button', {name: 'Проверить дубли: Основной контакт E2E', exact: true}).click();
  await page.getByRole('button', {name: 'Слияние: Дубликат контакта E2E', exact: true}).click();
  const merge = page.getByRole('region', {name: 'Слияние контактов', exact: true});
  await expect(merge.getByText('Останется: Основной контакт E2E', {exact: true})).toBeVisible();
  await expect(merge.getByRole('button', {name: 'Подтвердить слияние'})).toBeDisabled();
  await page.setViewportSize({width: 390, height: 844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await merge.getByRole('checkbox', {name: 'Взять из исходной: Телефон', exact: true}).check();
  await merge.getByRole('checkbox', {name: /Я проверил контакты/}).check();
  await merge.getByRole('button', {name: 'Подтвердить слияние', exact: true}).click();
  await expect(merge.getByRole('status')).toContainText('Контакты объединены');
  const result = await page.evaluate(async data => {
    const get = async (path: string) => (await fetch(`/api/v1${data.base}${path}`)).json();
    return {sourceStatus: (await fetch(`/api/v1${data.base}/contacts/${data.sourceId}`)).status,
      target: await get(`/contacts/${data.targetId}`), deal: await get(`/deals/${data.dealId}`),
      links: await get(`/deals/${data.dealId}/contacts`), thirdDeal: await get(`/deals/${data.thirdDealId}`),
      thirdLinks: await get(`/deals/${data.thirdDealId}/contacts`), projectLinks: await get(`/projects/${data.projectId}/contacts`), task: await get(`/tasks/${data.taskId}`)};
  }, data);
  expect(result.sourceStatus).toBe(404);
  expect(result.target.phone).toBe('+7 900 333 44 55');
  expect(result.deal.contact_id).toBe(data.targetId);
  expect(result.deal.contact_name).toBe('Основной контакт E2E');
  expect(result.links.map((row: {contact_id: string}) => row.contact_id)).toEqual([data.targetId]);
  expect(result.links[0].is_primary).toBe(true);
  expect(result.thirdDeal.contact_id).toBe(data.thirdId);
  expect(result.thirdLinks.filter((row: {is_primary: boolean}) => row.is_primary).map((row: {contact_id: string}) => row.contact_id)).toEqual([data.thirdId]);
  expect(result.projectLinks.map((row: {contact_id: string}) => row.contact_id)).toEqual([data.targetId]);
  expect(result.task.contact_id).toBe(data.targetId);
  await page.reload();
  await page.getByRole('button', {name: 'Клиенты', exact: true}).click();
  await page.getByRole('tab', {name: 'Контакты', exact: true}).click();
  await page.getByRole('button', {name: 'Основной контакт E2E', exact: true}).click();
  const contact = page.getByRole('dialog', {name: 'Контакты', exact: true});
  await contact.getByRole('button', {name: 'История слияний', exact: true}).click();
  await contact.getByText(/Квитанция слияния:/).click();
  await expect(contact.getByText('Исходная заметка контакта E2E', {exact: true})).toBeVisible();
});
