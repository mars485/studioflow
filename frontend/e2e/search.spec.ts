import {expect, test} from '@playwright/test';

test('search crosses entity types and opens exact objects in a non-default workspace', async ({page}) => {
  test.setTimeout(60000);
  await page.goto('/');
  const workspaceId = await page.evaluate(async () => {
    const post = async (path: string, data: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(data)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const stamp = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await post('/auth/register', {email: `${stamp}@example.com`, password: 'Search-E2E-password123', first_name: 'Search E2E'});
    await post('/workspaces', {name: 'Личная студия поиска'});
    const space = await post('/workspaces', {name: 'Рабочая студия поиска'});
    const base = `/workspaces/${space.id}`;
    const client = await post(`${base}/clients`, {name: 'Поиск E2E компания'});
    await post(`${base}/contacts`, {first_name: 'Поиск E2E контакт'});
    const pipelines = await (await fetch(`/api/v1${base}/pipelines`)).json();
    await post(`${base}/deals`, {title: 'Поиск E2E сделка', client_id: client.id, pipeline_id: pipelines[0].id, stage_id: pipelines[0].stages[0].id});
    const parent = await post(`${base}/tasks`, {title: 'Родитель отчёта'});
    await post(`${base}/tasks`, {title: 'Поиск E2E задача', parent_task_id: parent.id});
    const project = await post(`${base}/projects`, {title: 'Поиск E2E проект', client_id: client.id});
    const archived = await fetch(`/api/v1${base}/projects/${project.id}`, {method: 'PATCH',
      headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify({status: 'ARCHIVED'})});
    if (!archived.ok) throw new Error(await archived.text());
    return space.id;
  });
  await page.reload();
  const search = async () => {
    await page.getByRole('button', {name: 'Поиск', exact: true}).click();
    await page.getByLabel('Рабочее пространство').selectOption(workspaceId);
    await page.getByLabel('Поисковый запрос').fill('Поиск E2E');
    await page.getByRole('button', {name: 'Найти в студии'}).click();
    await expect(page.getByText('Найдено: 5 · запрос «Поиск E2E»')).toBeVisible();
  };
  for (const [name, dialog] of [
    ['задачу Поиск E2E задача', 'Карточка задачи'], ['проект Поиск E2E проект', 'Карточка проекта'],
    ['компанию Поиск E2E компания', 'Компании'], ['контакт Поиск E2E контакт', 'Контакты'], ['сделку Поиск E2E сделка', 'Карточка сделки'],
  ]) {
    await search();
    await page.getByRole('button', {name: `Открыть ${name}`, exact: true}).click();
    await expect(page.getByRole('dialog', {name: dialog, exact: true})).toBeVisible();
    await expect(page.getByLabel('Рабочее пространство', {exact: true})).toHaveValue(workspaceId);
    await page.getByRole('dialog', {name: dialog, exact: true}).getByRole('button', {name: 'Закрыть', exact: true}).click();
  }
});
