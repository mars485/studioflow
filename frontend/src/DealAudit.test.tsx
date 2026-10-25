import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import DealAudit from './DealAudit';

afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('loads historical identities and filters without offering mutation controls', async () => {
  const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify({total: 1, items: [{id: 'a1', deal_id: 'd1',
    actor_id: 'u1', actor_name: 'Менеджер', actor_kind: 'USER', action: 'UPDATED', fields: ['title'], created_at: '2026-10-24T12:00:00Z'}]})));
  vi.stubGlobal('fetch', fetchMock);
  render(<DealAudit base="/workspaces/w1"/>);
  expect(await screen.findByText('Изменены поля: title')).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Удалить'})).toBeNull();
  fireEvent.change(screen.getByLabelText('Операция аудита'), {target: {value: 'DELETED'}});
  fireEvent.click(screen.getByRole('button', {name: 'Применить фильтр аудита'}));
  await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.includes('action=DELETED'))).toBe(true));
});

it('reports denial without retaining private records and retries', async () => {
  let fail = true;
  vi.stubGlobal('fetch', vi.fn(async () => fail ? new Response(JSON.stringify({detail: 'Доступ запрещён'}), {status: 403}) :
    new Response(JSON.stringify({total: 0, items: []}))));
  render(<DealAudit base="/workspaces/w1"/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Доступ запрещён');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Повторить загрузку аудита'}));
  expect(await screen.findByText('Записей по выбранному фильтру нет.')).toBeTruthy();
});
