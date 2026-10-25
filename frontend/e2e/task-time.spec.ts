import {expect, test} from '@playwright/test';

test('manual time and server timer survive reload, completion closes the timer', async ({page}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const post = async (path: string, data: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(data)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    await post('/auth/register', {email: `time-${Date.now()}-${Math.random()}@example.com`, password: 'Timer-E2E-password123', first_name: 'Timer E2E'});
    const space = await post('/workspaces', {name: 'Timer E2E'});
    await post(`/workspaces/${space.id}/tasks`, {title: 'Время E2E'});
  });
  const open = async (completed = false) => {
    await page.reload();
    await page.getByRole('button', {name: 'Задачи', exact: true}).click();
    const cards = page.getByRole('article', {name: 'Открыть Время E2E'});
    await (completed ? page.locator('.kanbanCol').filter({hasText: 'Завершено'}).getByRole('article', {name: 'Открыть Время E2E'}) : cards).click();
  };
  await open();
  const drawer = page.getByRole('dialog', {name: 'Карточка задачи'});
  await drawer.getByLabel('Затрачено минут').fill('25');
  await drawer.getByLabel('Комментарий к времени').fill('Макет E2E');
  await drawer.getByRole('button', {name: 'Записать время'}).click();
  await expect(drawer.getByText(/Вручную · Макет E2E/)).toBeVisible();
  await drawer.getByRole('button', {name: 'Запустить таймер'}).click();
  await expect(drawer.getByRole('button', {name: 'Остановить таймер'})).toBeVisible();
  await drawer.getByLabel('Повторять задачу').check();
  await drawer.getByLabel('Интервал, суток').fill('7');
  await drawer.getByLabel('Следующих задач').fill('1');
  const savedRecurrence = page.waitForResponse(response => response.url().endsWith('/recurrence') && response.request().method() === 'PUT');
  await drawer.getByRole('button', {name: 'Сохранить повторение'}).click();
  expect((await savedRecurrence).ok()).toBe(true);
  await open();
  await expect(drawer.getByText(/Вручную · Макет E2E/)).toBeVisible();
  await expect(drawer.getByRole('button', {name: 'Остановить таймер'})).toBeVisible();
  await drawer.getByLabel('Статус', {exact: true}).selectOption({label: 'Завершено'});
  await drawer.getByRole('button', {name: 'Сохранить задачу'}).click();
  await expect(drawer.getByText(/Остановлен завершением задачи/)).toBeVisible();
  await expect(drawer.getByRole('button', {name: 'Открыть следующую задачу'})).toBeVisible();
  await open(true);
  await expect(drawer.getByRole('button', {name: 'Запустить таймер'})).toBeDisabled();
  await expect(drawer.getByText(/Остановлен завершением задачи/)).toBeVisible();
});
