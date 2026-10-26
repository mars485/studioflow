import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import EmployeeGroups from './EmployeeGroups';
import type {Member} from './api';

const members: Member[] = [{id: 'm1', user_id: 'u1', email: 'manager@example.com', first_name: 'Manager', role: 'MANAGER'}];
const group = {id: 'g1', name: 'Наблюдение', description: 'Без изменений задач', version: 1, user_ids: ['u1'], blocked_actions: ['tasks.write']};
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('preserves a failed group draft, selected members and module restrictions', async () => {
  let fail = true;
  const writes: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, options: RequestInit) => {
    if (options.method === 'GET') return response([]);
    writes.push(JSON.parse(String(options.body)));
    return fail ? response({detail: 'Группа не сохранена'}, 503) : response(group, 201);
  }));
  render(<EmployeeGroups base="/workspaces/w1" role="OWNER" members={members}/>);
  await screen.findByText('Групп пока нет.');
  fireEvent.click(screen.getByRole('button', {name: 'Новая группа'}));
  const form = screen.getByRole('form', {name: 'Форма группы'});
  fireEvent.change(within(form).getByLabelText('Название группы'), {target: {value: 'Наблюдение'}});
  fireEvent.click(within(form).getByRole('checkbox', {name: 'manager@example.com'}));
  fireEvent.click(within(form).getByRole('checkbox', {name: 'Задачи'}));
  fireEvent.click(within(form).getByRole('button', {name: 'Сохранить группу'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Группа не сохранена');
  expect((within(form).getByLabelText('Название группы') as HTMLInputElement).value).toBe('Наблюдение');
  expect((within(form).getByRole('checkbox', {name: 'Задачи'}) as HTMLInputElement).checked).toBe(true);
  fail = false; fireEvent.click(within(form).getByRole('button', {name: 'Сохранить группу'}));
  expect(await screen.findByText(/Группа сохранена/)).toBeTruthy();
  expect(writes[0]).toEqual(writes[1]);
  expect(writes[1]).toMatchObject({user_ids: ['u1'], blocked_actions: ['tasks.write']});
});

it('allows ADMIN to inspect groups but never offers mutation controls', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response([group])));
  render(<EmployeeGroups base="/workspaces/w1" role="ADMIN" members={members}/>);
  expect(await screen.findByText('Наблюдение')).toBeTruthy();
  expect(screen.getByText(/Запрещены изменения: Задачи/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Новая группа'})).toBeNull();
  expect(screen.queryByRole('button', {name: /Редактировать:/})).toBeNull();
  expect(screen.queryByRole('button', {name: /Удалить группу:/})).toBeNull();
});

it('sends the captured version and retains a stale edit instead of overwriting it', async () => {
  const writes: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, options: RequestInit) => {
    if (options.method === 'GET') return response([group]);
    writes.push(JSON.parse(String(options.body)));
    return response({detail: 'Группа изменена. Обновите список'}, 409);
  }));
  render(<EmployeeGroups base="/workspaces/w1" role="OWNER" members={members}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Редактировать: Наблюдение'}));
  fireEvent.change(screen.getByLabelText('Название группы'), {target: {value: 'Мой черновик'}});
  fireEvent.click(screen.getByRole('button', {name: 'Сохранить группу'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Группа изменена');
  expect((screen.getByLabelText('Название группы') as HTMLInputElement).value).toBe('Мой черновик');
  expect(writes[0]).toMatchObject({name: 'Мой черновик', expected_version: 1});
});

it('retries loading and reads the separate persistent group journal', async () => {
  let fail = true;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('/audit?')) return response([{id: 'a1', group_id: 'deleted-group', actor_name: 'Владелец', action: 'DELETED', fields: [], created_at: '2026-10-26T12:00:00Z'}]);
    return fail ? response({detail: 'Список недоступен'}, 503) : response([]);
  }));
  render(<EmployeeGroups base="/workspaces/w1" role="OWNER" members={members}/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Список недоступен');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Обновить группы'}));
  expect(await screen.findByText('Групп пока нет.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Открыть журнал групп'}));
  expect(await screen.findByText('deleted-group')).toBeTruthy();
});
