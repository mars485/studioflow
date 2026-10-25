import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import Clients from './Clients';
import type {Client} from './api';

let rows: Client[];
let fail: boolean;
beforeEach(() => {
  fail = false;
  rows = [{id: 'c1', type: 'COMPANY', name: 'Студия клиента', phone: '+7 900 123', email: 'client@example.com', website: null, notes: null}];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Workspace', role: 'OWNER'}]);
    if (url.endsWith('/contacts')) return response([]);
    if (options.method === 'POST') {
      if (fail) return response({detail: 'Ошибка компании'}, 503);
      const data = JSON.parse(String(options.body));
      const row: Client = {id: 'c2', type: 'COMPANY', name: data.name, phone: data.phone, email: data.email, website: data.website, notes: data.notes};
      rows.push(row); return response(row, 201);
    }
    if (url.endsWith('/clients')) return response(rows);
    if (url.endsWith('/deals')) return response([{id: 'd1', title: 'Связанная сделка', amount: '100', currency: 'RUB'}]);
    throw new Error(url);
  }));
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('opens an exact company target from global search after loading the directory', async () => {
  render(<Clients onOpenDeal={vi.fn()} initialWorkspaceId="w1" initialTarget={{kind: 'client', id: 'c1'}}/>);
  const dialog = await screen.findByRole('dialog', {name: 'Компании'});
  expect((within(dialog).getByLabelText('Название компании') as HTMLInputElement).value).toBe('Студия клиента');
});

it('does not turn a deleted search target into a blank company editor', async () => {
  render(<Clients onOpenDeal={vi.fn()} initialWorkspaceId="w1" initialTarget={{kind: 'client', id: 'deleted'}}/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Объект из поиска больше недоступен');
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('opens a company from its dedicated page and routes a linked deal to the right workspace', async () => {
  const onOpenDeal = vi.fn();
  render(<Clients onOpenDeal={onOpenDeal}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Студия клиента'}));
  const dialog = screen.getByRole('dialog', {name: 'Компании'});
  expect((within(dialog).getByLabelText('Рабочий телефон') as HTMLInputElement).value).toBe('+7 900 123');
  expect((screen.getByLabelText('Рабочее пространство') as HTMLSelectElement).disabled).toBe(true);
  fireEvent.click(await within(dialog).findByRole('button', {name: 'Связанная сделка'}));
  expect(onOpenDeal).toHaveBeenCalledWith('w1', 'd1');
});

it('preserves a failed company draft and creates it after retry', async () => {
  render(<Clients onOpenDeal={vi.fn()}/>);
  await screen.findByRole('button', {name: 'Студия клиента'});
  fireEvent.click(screen.getByRole('button', {name: 'Новая компания'}));
  const dialog = screen.getByRole('dialog', {name: 'Компании'});
  fireEvent.change(within(dialog).getByLabelText('Название компании'), {target: {value: 'Новая компания клиента'}});
  fail = true;
  fireEvent.click(within(dialog).getByRole('button', {name: 'Сохранить компанию'}));
  expect((await within(dialog).findByRole('alert')).textContent).toContain('Ошибка компании');
  expect((within(dialog).getByLabelText('Название компании') as HTMLInputElement).value).toBe('Новая компания клиента');
  fail = false;
  fireEvent.click(within(dialog).getByRole('button', {name: 'Сохранить компанию'}));
  expect(await within(dialog).findByRole('button', {name: 'Новая компания клиента'})).toBeTruthy();
});
