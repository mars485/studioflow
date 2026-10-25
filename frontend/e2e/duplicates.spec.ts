import {expect, test} from '@playwright/test';

test('duplicate candidates explain matching fields and open the existing company without merging', async ({page}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const post = async (path: string, body: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(body)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    await post('/auth/register', {email: `duplicates-${Date.now()}-${Math.random()}@example.com`, password: 'Duplicates-E2E-password123', first_name: 'Duplicates E2E'});
    const space = await post('/workspaces', {name: 'Контроль дублей E2E'});
    await post(`/workspaces/${space.id}/clients`, {name: 'Основная компания E2E', phone: '+7 (900) 123-45-67', email: 'same@example.com'});
    await post(`/workspaces/${space.id}/clients`, {name: 'Кандидат E2E', phone: '79001234567', email: 'same@example.com'});
  });
  await page.reload();
  await page.getByRole('button', {name: 'Клиенты', exact: true}).click();
  await page.getByRole('button', {name: 'Проверить дубли: Основная компания E2E', exact: true}).click();
  const candidates = page.getByRole('region', {name: 'Возможные дубли', exact: true});
  await expect(candidates.getByText(/Возможных дублей: 1/)).toBeVisible();
  await expect(candidates.getByText(/Совпадает: email, телефон/)).toBeVisible();
  await candidates.getByRole('button', {name: 'Сравнить: Кандидат E2E', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: 'Компании', exact: true});
  await expect(dialog.getByLabel('Название компании')).toHaveValue('Кандидат E2E');
  await dialog.getByRole('button', {name: 'Закрыть', exact: true}).click();
  await page.reload();
  await page.getByRole('button', {name: 'Клиенты', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Основная компания E2E', exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Кандидат E2E', exact: true})).toBeVisible();
});
