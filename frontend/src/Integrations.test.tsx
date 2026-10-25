import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import Integrations from './Integrations';

let role: string;
let fail: boolean;
let rows: object[];
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  role = 'OWNER'; fail = false; rows = [];
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), {status});
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Студия', role}]);
    if (url.endsWith('/pipelines')) return response([{id: 'p1', name: 'Продажи'}]);
    if (url.endsWith('/webhooks/destinations')) return response({destinations: []});
    if (url.includes('/webhooks')) return response([]);
    if (options.method === 'POST') {
      if (fail) return response({detail: 'Ошибка интеграции'}, 503);
      const data = JSON.parse(String(options.body));
      const row = {id: 't1', name: data.name, hint: '…secret', pipeline_id: 'p1', expires_at: '2027-01-01T10:00:00Z', revoked_at: null, created_at: '', last_used_at: null, scope: 'leads:create'};
      rows.push(row); return response({...row, token: 'sf_lead_one_time_secret'}, 201);
    }
    if (url.includes('/integration-tokens?')) return response(rows);
    if (url.includes('/integration-leads?')) return response([]);
    throw new Error(url);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});

it('shows a new secret once and never restores it from token listings', async () => {
  const props = {onOpenDeal: vi.fn()};
  const view = render(<Integrations {...props}/>);
  await screen.findByText('Токенов пока нет.');
  fireEvent.change(screen.getByLabelText('Название интеграции'), {target: {value: 'ITG'}});
  fireEvent.click(screen.getByRole('button', {name: 'Создать интеграционный токен'}));
  const secret = await screen.findByLabelText('Новый API-токен');
  expect((secret as HTMLTextAreaElement).value).toBe('sf_lead_one_time_secret');
  fireEvent.click(screen.getByRole('button', {name: 'Скрыть секрет'}));
  expect(screen.queryByLabelText('Новый API-токен')).toBeNull();
  view.unmount(); render(<Integrations {...props}/>);
  await screen.findByText('ITG', {exact: true});
  expect(screen.queryByLabelText('Новый API-токен')).toBeNull();
});

it('preserves integration settings on API failure', async () => {
  render(<Integrations onOpenDeal={vi.fn()}/>);
  await screen.findByText('Токенов пока нет.');
  fireEvent.change(screen.getByLabelText('Название интеграции'), {target: {value: 'Не потерять'}});
  fail = true;
  fireEvent.click(screen.getByRole('button', {name: 'Создать интеграционный токен'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Ошибка интеграции');
  expect((screen.getByLabelText('Название интеграции') as HTMLInputElement).value).toBe('Не потерять');
  fail = false;
  fireEvent.click(screen.getByRole('button', {name: 'Создать интеграционный токен'}));
  await screen.findByLabelText('Новый API-токен');
});

it('does not load integration secrets or logs for a manager', async () => {
  role = 'MANAGER';
  render(<Integrations onOpenDeal={vi.fn()}/>);
  expect((await screen.findByRole('alert')).textContent).toContain('только владельцу');
  await waitFor(() => expect(fetchMock.mock.calls.every(([url]) => url === '/api/v1/workspaces')).toBe(true));
});
