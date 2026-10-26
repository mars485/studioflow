import {expect, test} from '@playwright/test';

test('owner group restrictions block manager writes, preserve drafts and can be lifted', async ({page, browser}) => {
  await page.goto('/');
  const data = await page.evaluate(async () => {
    const post = async (path: string, body?: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: body === undefined ? undefined : JSON.stringify(body)});
      if (!response.ok) throw new Error(await response.text());
      return response.status === 204 ? null : response.json();
    };
    const managerEmail = `group-manager-${Date.now()}-${Math.random()}@example.com`;
    const managerPassword = 'Employee-Groups-E2E-password123';
    await post('/auth/register', {email: managerEmail, password: managerPassword, first_name: 'Group manager E2E'});
    await post('/auth/logout');
    await post('/auth/register', {email: `group-owner-${Date.now()}-${Math.random()}@example.com`, password: 'Employee-Groups-Owner-E2E-password123', first_name: 'Group owner E2E'});
    const workspace = await post('/workspaces', {name: 'Группы сотрудников E2E'});
    const base = `/workspaces/${workspace.id}`;
    await post(base + '/members', {email: managerEmail, role: 'MANAGER'});
    await post(base + '/tasks', {title: 'Исходная задача групп E2E'});
    return {base, managerEmail, managerPassword};
  });
  await page.reload();
  await page.getByRole('button', {name: 'Настройки', exact: true}).click();
  await page.getByRole('button', {name: 'Открыть группы сотрудников', exact: true}).click();
  const groups = page.getByRole('region', {name: 'Группы сотрудников', exact: true});
  await expect(groups.getByText('Групп пока нет.', {exact: true})).toBeVisible();
  await groups.getByRole('button', {name: 'Новая группа', exact: true}).click();
  const form = groups.getByRole('form', {name: 'Форма группы', exact: true});
  await form.getByLabel('Название группы', {exact: true}).fill('Только просмотр задач E2E');
  await form.getByRole('checkbox', {name: data.managerEmail, exact: true}).check();
  await form.getByRole('checkbox', {name: 'Задачи', exact: true}).check();
  await form.getByRole('button', {name: 'Сохранить группу', exact: true}).click();
  await expect(groups.getByRole('status')).toContainText('Группа сохранена');
  await page.setViewportSize({width: 390, height: 844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  const managerContext = await browser.newContext();
  const managerPage = await managerContext.newPage();
  try {
    await managerPage.goto(new URL('/', page.url()).href);
    await managerPage.evaluate(async ({managerEmail, managerPassword}) => {
      const response = await fetch('/api/v1/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify({email: managerEmail, password: managerPassword})});
      if (!response.ok) throw new Error(await response.text());
    }, data);
    await managerPage.reload();
    await managerPage.getByRole('button', {name: 'Задачи', exact: true}).click();
    await expect(managerPage.getByText('Исходная задача групп E2E', {exact: true})).toBeVisible();
    await managerPage.getByRole('button', {name: 'Новая задача', exact: true}).click();
    const task = managerPage.getByRole('dialog', {name: 'Новая задача', exact: true});
    await task.getByLabel('Название задачи', {exact: true}).fill('Черновик после отказа группы E2E');
    await task.getByRole('button', {name: 'Создать задачу', exact: true}).click();
    await expect(task.getByRole('alert')).toContainText('запрещено настройками группы');
    await expect(task.getByLabel('Название задачи')).toHaveValue('Черновик после отказа группы E2E');
    const permissions = await managerPage.evaluate(async ({base}) => (await fetch(`/api/v1${base}/group-permissions`)).json(), data);
    expect(permissions.blocked_actions).toEqual(['tasks.write']);

    await groups.getByRole('button', {name: 'Редактировать: Только просмотр задач E2E', exact: true}).click();
    await groups.getByRole('form', {name: 'Форма группы', exact: true}).getByRole('checkbox', {name: 'Задачи', exact: true}).uncheck();
    await groups.getByRole('button', {name: 'Сохранить группу', exact: true}).click();
    await expect(groups.getByRole('status')).toContainText('Группа сохранена');
    await task.getByRole('button', {name: 'Создать задачу', exact: true}).click();
    await expect(task).toHaveCount(0);
    await expect(managerPage.getByText('Черновик после отказа группы E2E', {exact: true})).toBeVisible();
    await managerPage.getByRole('button', {name: 'Настройки', exact: true}).click();
    await expect(managerPage.getByRole('button', {name: 'Открыть группы сотрудников', exact: true})).toHaveCount(0);
    await groups.getByRole('button', {name: 'Открыть журнал групп', exact: true}).click();
    const journal = groups.getByRole('region', {name: 'Журнал изменений групп', exact: true});
    await expect(journal.getByText(/CREATED/)).toBeVisible();
    await expect(journal.getByText(/UPDATED/)).toBeVisible();
  } finally {await managerContext.close();}
});
