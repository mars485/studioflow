import {expect, test} from '@playwright/test';

test('deal → invoice → partial/full payment → signed act persists', async ({page}) => {
  await page.goto('/');
  // Setup only in this disposable E2E stack; exercise finance through the UI.
  const setup = await page.evaluate(async () => {
    const post = async (path: string, data: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(data)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const stamp = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await post('/auth/register', {email: `${stamp}@example.com`, password: 'E2E-password-12345', first_name: 'Finance E2E'});
    const workspace = await post('/workspaces', {name: `Finance ${stamp}`});
    const base = `/workspaces/${workspace.id}`;
    const client = await post(`${base}/clients`, {name: 'Заказчик E2E'});
    const pipelines = await (await fetch(`/api/v1${base}/pipelines`)).json();
    await post(`${base}/deals`, {title: 'Сайт E2E', client_id: client.id, pipeline_id: pipelines[0].id, stage_id: pipelines[0].stages[0].id, amount: '100.25'});
    return workspace.id;
  });
  await page.reload();
  await page.getByRole('button', {name: 'Финансы', exact: true}).click();
  await page.getByRole('button', {name: 'Добавить организацию'}).click();
  const organization = page.getByRole('dialog', {name: 'Реквизиты организации'});
  await organization.getByLabel('Название организации').fill('Исполнитель E2E');
  await organization.getByLabel('ИНН организации').fill('1234567890');
  await organization.getByLabel('Банк', {exact: true}).fill('Банк E2E');
  await organization.getByRole('button', {name: 'Сохранить организацию'}).click();
  await expect(organization).not.toBeVisible();
  await page.getByRole('button', {name: 'Новый счёт', exact: true}).click();
  const form = page.getByRole('dialog', {name: 'Новый счёт'});
  await form.getByLabel('Сделка счёта').selectOption({label: 'Сайт E2E'});
  await expect(form.getByLabel('Сумма счёта')).toHaveValue('100.25');
  await form.getByRole('button', {name: 'Создать счёт'}).click();
  const drawer = page.getByRole('dialog', {name: 'Карточка счёта'});
  await expect(drawer.getByRole('region', {name: 'Печатная форма счёта'})).toContainText('Исполнитель E2E');
  await drawer.getByRole('button', {name: 'Выставить счёт'}).click();
  await drawer.getByLabel('Сумма платежа').fill('40.10');
  await drawer.getByRole('button', {name: 'Добавить платёж'}).click();
  await expect(drawer.getByRole('status', {name: 'Статус оплаты'})).toContainText('Оплачен частично');
  await drawer.getByRole('button', {name: 'Закрыть'}).click();
  await page.reload();
  await page.getByRole('button', {name: 'Финансы', exact: true}).click();
  await expect(page.getByLabel('Рабочее пространство')).toHaveValue(setup);
  await page.getByRole('button', {name: 'Счёт №1', exact: true}).click();
  await expect(drawer.getByRole('status', {name: 'Статус оплаты'})).toContainText('Оплачен частично');
  await drawer.getByLabel('Сумма платежа').fill('60.15');
  await drawer.getByRole('button', {name: 'Добавить платёж'}).click();
  await expect(drawer.getByRole('status', {name: 'Статус оплаты'})).toContainText('Оплачен ·');
  await drawer.getByRole('button', {name: 'Создать акт'}).click();
  await drawer.getByRole('button', {name: 'Отметить подписанным №1'}).click();
  await expect(drawer.getByText(/Акт №1.*Подписан/)).toBeVisible();
  // Print CSS must expose only the invoice, not CRM/sidebar contents.
  await page.emulateMedia({media: 'print'});
  await expect(page.locator('.invoicePrint')).toBeVisible();
  expect(await page.locator('.sidebar').evaluate(el => getComputedStyle(el).display)).toBe('none');
  const pdf = await page.pdf({format: 'A4'});
  expect(pdf.length).toBeGreaterThan(1000);
});
