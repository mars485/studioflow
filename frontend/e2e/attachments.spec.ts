import {expect, test} from '@playwright/test';

test('actual attachment bytes survive reload and can be removed', async ({page}) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const post = async (path: string, data: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(data)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const stamp = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await post('/auth/register', {email: `${stamp}@example.com`, password: 'File-E2E-password123', first_name: 'File E2E'});
    const workspace = await post('/workspaces', {name: 'Files E2E'});
    const base = `/workspaces/${workspace.id}`;
    const client = await post(`${base}/clients`, {name: 'Клиент файлов'});
    const pipelines = await (await fetch(`/api/v1${base}/pipelines`)).json();
    await post(`${base}/deals`, {title: 'Файлы E2E', client_id: client.id, pipeline_id: pipelines[0].id, stage_id: pipelines[0].stages[0].id});
  });
  await page.reload();
  await page.getByRole('article', {name: 'Открыть Файлы E2E'}).click();
  const drawer = page.getByRole('dialog', {name: 'Карточка сделки'});
  const bytes = Buffer.from('Бриф клиента\n\0Binary bytes\n', 'utf8');
  await drawer.getByLabel('Файл', {exact: true}).setInputFiles({name: 'brief.txt', mimeType: 'text/plain', buffer: bytes});
  await drawer.getByRole('button', {name: 'Загрузить файл'}).click();
  await expect(drawer.getByRole('link', {name: 'Скачать brief.txt'})).toBeVisible();
  await page.reload();
  await page.getByRole('article', {name: 'Открыть Файлы E2E'}).click();
  const downloadEvent = page.waitForEvent('download');
  await drawer.getByRole('link', {name: 'Скачать brief.txt'}).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe('brief.txt');
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).equals(bytes)).toBe(true);
  await drawer.getByRole('button', {name: 'Удалить вложение brief.txt'}).click();
  await expect(drawer.getByRole('link', {name: 'Скачать brief.txt'})).not.toBeVisible();
});
