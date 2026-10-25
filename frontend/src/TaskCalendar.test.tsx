import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import TaskCalendar, {dayKey, monthDays, occursOn} from './TaskCalendar';
import {loadTasks, localDateTime, type Task} from './api';

const task = (overrides: Partial<Task> = {}): Task => ({id: 't1', workspace_id: 'w1', title: 'Отчёт', description: null,
  status_id: 'st1', status_name: 'Сделать', is_final: false, priority: 'MEDIUM', assignee_user_id: null, creator_user_id: null,
  completed_by_user_id: null, start_at: null, due_at: null, estimate_minutes: null, deal_id: null, project_id: null,
  contact_id: null, parent_task_id: null, completed_at: null, created_at: '', updated_at: '', checklist_done: 0, checklist_total: 0, ...overrides});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('builds six Monday-first weeks across year boundaries', () => {
  const days = monthDays(new Date(2026, 11, 1));
  expect(days).toHaveLength(42);
  expect(days[0].getDay()).toBe(1);
  expect(dayKey(days[0])).toBe('2026-11-30');
  expect(dayKey(days.at(-1)!)).toBe('2027-01-10');
  expect(new Set(days.map(dayKey)).size).toBe(42);
});

it('uses the same browser-local date as the task editor and includes multi-day ranges', () => {
  const instant = '2026-12-31T23:30:00-06:00';
  expect(occursOn(task({due_at: instant}), localDateTime(instant).slice(0, 10))).toBe(true);
  const range = task({start_at: new Date(2026, 11, 31, 22).toISOString(), due_at: new Date(2027, 0, 2, 1).toISOString()});
  expect(occursOn(range, '2027-01-01')).toBe(true);
  expect(occursOn(range, '2027-01-03')).toBe(false);
  expect(occursOn(task(), '2027-01-01')).toBe(false);
});

it('navigates months, opens tasks and creates on a chosen day', () => {
  const onOpen = vi.fn(), onCreate = vi.fn();
  render(<TaskCalendar tasks={[task({due_at: new Date(2027, 0, 1, 18).toISOString()})]} members={[]}
    initialMonth={new Date(2026, 11, 1)} onOpen={onOpen} onCreate={onCreate}/>);
  fireEvent.click(screen.getByRole('button', {name: 'Следующий месяц'}));
  expect(screen.getByRole('heading', {name: /январь 2027/})).toBeTruthy();
  fireEvent.click(within(screen.getByRole('region', {name: 'День 2027-01-01'})).getByRole('button', {name: 'Открыть задачу Отчёт'}));
  expect(onOpen).toHaveBeenCalledWith('t1');
  fireEvent.click(screen.getByRole('button', {name: 'Создать задачу 2027-01-03'}));
  expect(onCreate).toHaveBeenCalledWith('2027-01-03');
  fireEvent.click(screen.getByRole('button', {name: 'Предыдущий месяц'}));
  expect(screen.getByRole('heading', {name: /декабрь 2026/})).toBeTruthy();
});

it('keeps unscheduled tasks visible and filters assignee and completed tasks', () => {
  render(<TaskCalendar tasks={[task(), task({id: 't2', title: 'Завершённая', is_final: true, assignee_user_id: 'u1'})]}
    members={[{id: 'm1', user_id: 'u1', first_name: 'Анна', email: 'anna@example.com', role: 'MANAGER'}]}
    onOpen={vi.fn()} onCreate={vi.fn()}/>);
  const unscheduled = screen.getByRole('region', {name: 'Задачи без дат'});
  expect(within(unscheduled).getAllByRole('button')).toHaveLength(2);
  fireEvent.click(screen.getByLabelText('Показывать завершённые'));
  expect(within(unscheduled).getAllByRole('button')).toHaveLength(1);
  fireEvent.change(screen.getByLabelText('Исполнитель календаря'), {target: {value: 'u1'}});
  expect(within(unscheduled).queryAllByRole('button')).toHaveLength(0);
});

it('loads later task pages, preserving filters and cancellation signal', async () => {
  const controller = new AbortController();
  const firstPage = Array.from({length: 500}, (_, index) => task({id: String(index)}));
  const mock = vi.fn(async (url: string, _options: RequestInit) => new Response(JSON.stringify(url.includes('offset=0') ? firstPage : [task({id: 'last'})]), {status: 200}));
  vi.stubGlobal('fetch', mock);
  const rows = await loadTasks('/workspaces/w1', controller.signal, {project_id: 'p1'});
  expect(rows).toHaveLength(501);
  expect(rows.at(-1)!.id).toBe('last');
  expect(mock.mock.calls.map(([url]) => url)).toEqual([
    '/api/v1/workspaces/w1/tasks?project_id=p1&limit=500&offset=0',
    '/api/v1/workspaces/w1/tasks?project_id=p1&limit=500&offset=500']);
  expect(mock.mock.calls.every(([, options]) => options.signal === controller.signal)).toBe(true);
});
