import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import TaskTime, {type TimeEntry} from './TaskTime';

let entries: TimeEntry[];
let timer: TimeEntry | null;
let fail: boolean;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  entries = []; timer = null; fail = false;
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});
    if (method !== 'GET' && fail) return response({detail: 'Ошибка времени'}, 503);
    if (url.endsWith('/time-timer')) return response(timer);
    if (method === 'GET') return response({items: entries, total_seconds: entries.reduce((n, row) => n + row.seconds, 0), timezone: 'Asia/Yekaterinburg', today: '2026-10-24'});
    if (url.endsWith('/stop')) {
      timer = null; entries = entries.map(row => ({...row, is_running: false, seconds: 65, ended_at: '2026-10-24T12:01:05Z'})); return response(entries[0]);
    }
    const running = url.endsWith('/timer');
    const row: TimeEntry = {id: 'e1', task_id: 't1', task_title: 'Работа', author_name: 'Tester', worked_on: data.worked_on || '2026-10-24',
      seconds: running ? 0 : data.minutes * 60, comment: data.comment, started_at: running ? '2026-10-24T12:00:00Z' : null,
      ended_at: null, is_running: running, elapsed_seconds: 0, can_edit: true, stop_reason: null};
    entries = [row]; if (running) timer = row;
    return response(row, 201);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});
const view = () => render(<TaskTime base="/workspaces/w1" taskId="t1" isFinal={false}/>);

it('preserves manual draft and request key on failure, then reloads saved time', async () => {
  const rendered = view();
  await screen.findByText('Записей времени нет.');
  fireEvent.change(screen.getByLabelText('Затрачено минут'), {target: {value: '25'}});
  fireEvent.change(screen.getByLabelText('Комментарий к времени'), {target: {value: 'Макет'}});
  fail = true; fireEvent.click(screen.getByRole('button', {name: 'Записать время'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Ошибка времени');
  expect((screen.getByLabelText('Затрачено минут') as HTMLInputElement).value).toBe('25');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Записать время'}));
  await screen.findByText(/Вручную · Макет/);
  const calls = fetchMock.mock.calls.filter(([, options]) => options.method === 'POST');
  expect(JSON.parse(String(calls[0][1].body)).request_key).toBe(JSON.parse(String(calls[1][1].body)).request_key);
  rendered.unmount(); view();
  expect(await screen.findByText(/Вручную · Макет/)).toBeTruthy();
});

it('restores a running timer on remount and stops the persistent entry', async () => {
  const rendered = view();
  fireEvent.click(await screen.findByRole('button', {name: 'Запустить таймер'}));
  await screen.findByRole('button', {name: 'Остановить таймер'});
  rendered.unmount(); view();
  fireEvent.click(await screen.findByRole('button', {name: 'Остановить таймер'}));
  await waitFor(() => expect(timer).toBeNull());
  expect(await screen.findByText(/0 ч 1 мин 5 с · Таймер/)).toBeTruthy();
});
