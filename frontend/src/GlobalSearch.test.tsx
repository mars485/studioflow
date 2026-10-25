import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import GlobalSearch from './GlobalSearch';

let fail: boolean;
let calls: string[];
beforeEach(() => {
  fail = false; calls = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    if (url.endsWith('/workspaces')) return new Response(JSON.stringify([{id: 'w1', name: 'Студия', role: 'MANAGER'}]));
    if (fail) return new Response(JSON.stringify({detail: 'Ошибка поиска'}), {status: 503});
    return new Response(JSON.stringify({items: [{kind: 'task', id: 't1', label: 'Отчёт', state: 'Сделать'}], total: 1}));
  }));
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('searches explicitly and routes a result to its exact workspace and object', async () => {
  const onOpen = vi.fn();
  render(<GlobalSearch onOpen={onOpen}/>);
  fireEvent.change(await screen.findByLabelText('Поисковый запрос'), {target: {value: 'Отчёт'}});
  expect(calls.some(url => url.includes('/search?'))).toBe(false);
  fireEvent.click(screen.getByRole('button', {name: 'Найти в студии'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Открыть задачу Отчёт'}));
  expect(onOpen).toHaveBeenCalledWith({kind: 'task', id: 't1', workspaceId: 'w1'});
});

it('preserves a failed search and retries the same query', async () => {
  fail = true; render(<GlobalSearch onOpen={vi.fn()}/>);
  fireEvent.change(await screen.findByLabelText('Поисковый запрос'), {target: {value: 'Отчёт'}});
  fireEvent.click(screen.getByRole('button', {name: 'Найти в студии'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Ошибка поиска');
  expect((screen.getByLabelText('Поисковый запрос') as HTMLInputElement).value).toBe('Отчёт');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Повторить поиск'}));
  expect(await screen.findByRole('button', {name: 'Открыть задачу Отчёт'})).toBeTruthy();
});
