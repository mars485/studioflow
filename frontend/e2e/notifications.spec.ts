import {expect, test} from '@playwright/test';

test('addressed mention reaches only recipient and opens the correct workspace deal', async ({page, browser}) => {
  await page.goto('/');
  const setup = await page.evaluate(async () => {
    const post = async (path: string, data: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(data)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const stamp = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await post('/auth/register', {email: `sender-${stamp}@example.com`, password: 'Mention-E2E-password123', first_name: 'Автор E2E'});
    const workspace = await post('/workspaces', {name: 'Адресная студия'});
    const base = `/workspaces/${workspace.id}`;
    const client = await post(`${base}/clients`, {name: 'Клиент упоминания'});
    const pipelines = await (await fetch(`/api/v1${base}/pipelines`)).json();
    await post(`${base}/deals`, {title: 'Сделка упоминания', client_id: client.id, pipeline_id: pipelines[0].id, stage_id: pipelines[0].stages[0].id});
    return {workspaceId: workspace.id, recipientEmail: `recipient-${stamp}@example.com`};
  });
  const receiver = await browser.newPage();
  try {
    await receiver.goto(new URL('/', page.url()).href);
    const userId = await receiver.evaluate(async ({email}) => {
      const response = await fetch('/api/v1/auth/register', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'},
        body: JSON.stringify({email, password: 'Mention-E2E-password123', first_name: 'Адресат E2E'})});
      if (!response.ok) throw new Error(await response.text());
      const user = await response.json();
      await fetch('/api/v1/workspaces', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify({name: 'Личная студия'})});
      return user.id;
    }, {email: setup.recipientEmail});
    await page.evaluate(async data => {
      const response = await fetch(`/api/v1/workspaces/${data.workspaceId}/members`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify({email: data.recipientEmail, role: 'MANAGER'})});
      if (!response.ok) throw new Error(await response.text());
    }, setup);
    await page.reload();
    await page.getByRole('article', {name: 'Открыть Сделка упоминания'}).click();
    const drawer = page.getByRole('dialog', {name: 'Карточка сделки'});
    await drawer.getByLabel('Тип записи').selectOption('MENTION');
    await drawer.getByLabel('Адресат упоминания').selectOption(userId);
    await drawer.getByLabel('Новая заметка').fill('Проверьте бриф E2E');
    await drawer.getByRole('button', {name: 'Добавить в историю'}).click();
    await expect(drawer.getByText('Адресат: Адресат E2E')).toBeVisible();
    await drawer.getByRole('button', {name: 'Закрыть'}).click();
    await page.getByRole('button', {name: 'Уведомления', exact: true}).click();
    await expect(page.getByText('Уведомлений нет.')).toBeVisible();
    await receiver.reload();
    await receiver.getByRole('button', {name: 'Уведомления', exact: true}).click();
    await receiver.getByLabel('Рабочее пространство').selectOption(setup.workspaceId);
    await expect(receiver.getByText('Проверьте бриф E2E')).toBeVisible();
    await receiver.getByRole('button', {name: 'Открыть сделку Сделка упоминания'}).click();
    await expect(receiver.getByRole('dialog', {name: 'Карточка сделки'})).toContainText('Сделка упоминания');
    await expect(receiver.getByLabel('Рабочее пространство')).toHaveValue(setup.workspaceId);
    await receiver.getByRole('dialog', {name: 'Карточка сделки'}).getByRole('button', {name: 'Закрыть'}).click();
    await receiver.reload();
    await receiver.getByRole('button', {name: 'Уведомления', exact: true}).click();
    await receiver.getByLabel('Рабочее пространство').selectOption(setup.workspaceId);
    await expect(receiver.getByText('Прочитано', {exact: true})).toBeVisible();
  } finally {await receiver.close();}
});
