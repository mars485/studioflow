import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import Notifications, {type InboxNotification} from './Notifications';

let rows: InboxNotification[];
let fail: boolean;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fail = false;
  rows = [{id: 'n1', workspace_id: 'w1', activity_id: 'a1', deal_id: 'd1', deal_title: 'Сайт', body: 'Проверьте бриф', author_name: 'Автор', read_at: null, created_at: '2026-10-24T10:00:00Z'}];
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status});
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Студия', role: 'MANAGER'}]);
    if (url.endsWith('/unread-count')) return response({count: rows.filter(row => !row.read_at).length});
    if (options.method === 'POST') {
      if (fail) return response({detail: 'Ошибка чтения'}, 503);
      rows = rows.map(row => ({...row, read_at: '2026-10-24T11:00:00Z'})); return response(null, 204);
    }
    return response(rows.filter(row => !url.includes('unread_only=true') || !row.read_at));
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('loads a private inbox and keeps read status after reload', async () => {
  const props = {onOpenDeal: vi.fn()};
  const view = render(<Notifications {...props}/>);
  await screen.findByText('Проверьте бриф');
  fireEvent.click(screen.getByRole('button', {name: 'Прочитать уведомление Сайт'}));
  await screen.findByText('Прочитано');
  expect(rows[0].read_at).toBeTruthy();
  view.unmount(); render(<Notifications {...props}/>);
  expect(await screen.findByText('Прочитано')).toBeTruthy();
  expect(screen.getByText('Непрочитанных: 0')).toBeTruthy();
});

it('marks an opened notification read and routes to its exact workspace and deal', async () => {
  const onOpenDeal = vi.fn();
  render(<Notifications onOpenDeal={onOpenDeal}/>);
  await screen.findByText('Проверьте бриф');
  fireEvent.click(screen.getByRole('button', {name: 'Открыть сделку Сайт'}));
  await waitFor(() => expect(onOpenDeal).toHaveBeenCalledWith('w1', 'd1'));
  expect(rows[0].read_at).toBeTruthy();
});

it('keeps a failed read visible and permits retry without hiding the notification', async () => {
  render(<Notifications onOpenDeal={vi.fn()}/>);
  await screen.findByText('Проверьте бриф');
  fail = true;
  fireEvent.click(screen.getByRole('button', {name: 'Прочитать уведомление Сайт'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Ошибка чтения');
  expect(rows[0].read_at).toBeNull();
  expect(screen.getByText('Проверьте бриф')).toBeTruthy();
  fail = false;
  fireEvent.click(screen.getByRole('button', {name: 'Прочитать уведомление Сайт'}));
  await screen.findByText('Прочитано');
});
