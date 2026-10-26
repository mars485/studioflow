import {randomUUID} from 'node:crypto';
import {expect, test} from '@playwright/test';

test('structured website lead preserves source context and does not duplicate on retry', async ({page, request}) => {
  await page.goto('/');
  const config = await page.evaluate(async () => {
    const post = async (path: string, body: unknown) => {
      const response = await fetch(`/api/v1${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-StudioFlow-Request': '1'}, body: JSON.stringify(body)});
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    await post('/auth/register', {email: `website-${Date.now()}-${Math.random()}@example.com`, password: 'Website-Intake-E2E-password123', first_name: 'Website owner'});
    const workspace = await post('/workspaces', {name: 'Website intake isolated E2E'});
    const base = `/workspaces/${workspace.id}`;
    const token = await post(base + '/integration-tokens', {name: 'Synthetic website E2E', expires_days: 1});
    return {base, token: token.token, tokenId: token.id};
  });
  const headers = {'Authorization': `Bearer ${config.token}`, 'X-StudioFlow-Request': '1'};
  const data = {request_key: randomUUID(), form_kind: 'audit', name: 'Посетитель E2E', contact: '@website_e2e',
    email: 'visitor@example.com', website: 'https://visitor.example/', message: 'Синтетическая заявка для изолированной проверки',
    source_url: 'https://itgsystem.ru/audit', submitted_at: '2026-10-26T09:00:00Z', privacy_consent: true,
    audit_email_consent: true, policy_version: 'policy-e2e-v1', utm_source: 'search-e2e', utm_campaign: 'campaign-'.repeat(25)};
  const first = await request.post('/api/v1/integrations/website-leads', {headers, data});
  expect(first.status()).toBe(201);
  const receipt = await first.json();
  const replay = await request.post('/api/v1/integrations/website-leads', {headers, data});
  expect(replay.status()).toBe(200);
  expect((await replay.json()).id).toBe(receipt.id);
  const conflict = await request.post('/api/v1/integrations/website-leads', {headers, data: {...data, policy_version: 'changed'}});
  expect(conflict.status()).toBe(409);
  await page.reload();
  await page.getByRole('button', {name: 'Интеграции', exact: true}).click();
  const context = page.getByText('Контекст заявки сайта · Аудит', {exact: true});
  await expect(context).toHaveCount(1);
  await context.click();
  await expect(page.getByText('@website_e2e', {exact: true})).toBeVisible();
  await expect(page.getByText('Согласие заявлено источником; не рекламная подписка', {exact: true})).toBeVisible();
  await expect(page.getByText('policy-e2e-v1', {exact: true})).toBeVisible();
  await page.setViewportSize({width: 390, height: 844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const draftDownload = page.waitForEvent('download');
  await page.getByRole('link', {name: 'Скачать черновик n8n (неактивный)', exact: true}).click();
  expect((await draftDownload).suggestedFilename()).toBe('itg-website-intake.draft.json');
  const persisted = await page.evaluate(async ({base, clientId, dealId}) => {
    const get = async (path: string) => (await fetch(`/api/v1${base}${path}`)).json();
    return {client: await get(`/clients/${clientId}`), deals: await get('/deals'), deal: await get(`/deals/${dealId}`)};
  }, {...config, clientId: receipt.client_id, dealId: receipt.deal_id});
  expect(persisted.client.type).toBe('PERSON');
  expect(persisted.client.phone).toBeNull();
  expect(persisted.client.website).toBe(data.website);
  expect(persisted.deals).toHaveLength(1);
  expect(persisted.deal.utm_source).toBe('search-e2e');
  await page.reload();
  await page.getByRole('button', {name: 'Интеграции', exact: true}).click();
  await context.click();
  await expect(page.getByText('policy-e2e-v1', {exact: true})).toBeVisible();
  page.once('dialog', dialog => void dialog.accept());
  await page.getByRole('button', {name: 'Отозвать токен Synthetic website E2E', exact: true}).click();
  await expect(page.getByText(/^Отозван · Последний приём:/)).toBeVisible();
  expect((await request.post('/api/v1/integrations/website-leads', {headers, data})).status()).toBe(401);
});
