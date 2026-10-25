import {expect, test} from '@playwright/test';

test.use({timezoneId: 'Asia/Yekaterinburg'});
test('calendar day creation and edited deadline persist across reload', async ({page}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const post = async (path: string, data: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(data)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const stamp = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await post('/auth/register', {email: `${stamp}@example.com`, password: 'Calendar-E2E-password123', first_name: 'Calendar E2E'});
    await post('/workspaces', {name: 'Calendar E2E'});
  });
  await page.reload();
  await page.getByRole('button', {name: 'Задачи', exact: true}).click();
  await page.getByRole('button', {name: 'Календарь', exact: true}).click();
  const calendar = page.getByRole('region', {name: 'Календарь задач', exact: true});
  const now = await page.evaluate(() => {const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-15`;});
  await calendar.getByRole('button', {name: `Создать задачу ${now}`}).click();
  const form = page.getByRole('dialog', {name: 'Новая задача'});
  await expect(form.getByLabel('Крайний срок')).toHaveValue(`${now}T18:00`);
  await form.getByLabel('Название задачи').fill('Календарная задача E2E');
  await form.getByRole('button', {name: 'Создать задачу'}).click();
  const originalDay = calendar.getByRole('region', {name: `День ${now}`});
  await originalDay.getByRole('button', {name: 'Открыть задачу Календарная задача E2E'}).click();
  const drawer = page.getByRole('dialog', {name: 'Карточка задачи'});
  const next = now.slice(0, 8) + '16';
  await drawer.getByLabel('Крайний срок').fill(`${next}T00:30`);
  await drawer.getByRole('button', {name: 'Сохранить задачу'}).click();
  await drawer.getByRole('button', {name: 'Закрыть'}).click();
  await expect(calendar.getByRole('region', {name: `День ${next}`})).toContainText('Календарная задача E2E');
  await expect(originalDay).not.toContainText('Календарная задача E2E');
  await page.reload();
  await page.getByRole('button', {name: 'Задачи', exact: true}).click();
  await page.getByRole('button', {name: 'Календарь', exact: true}).click();
  await expect(calendar.getByRole('region', {name: `День ${next}`})).toContainText('Календарная задача E2E');
});
