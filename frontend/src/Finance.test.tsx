import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Finance from './Finance';
import type {Invoice, Organization} from './financeTypes';

let role: string;
let fail: boolean;
let rows: Invoice[];
let organizations: Organization[];
let fetchMock: ReturnType<typeof vi.fn>;
const organization: Organization = {id: 'o1', name: 'Студия', tax_id: '1234567890', tax_branch: '', address: 'Адрес', bank: 'Банк', bank_account: '123', bank_code: '123'};
const invoice = (): Invoice => ({id: 'i1', number: 1, issued_on: '2026-10-24', client_id: 'c1', organization_id: 'o1', deal_id: null,
  project_id: null, manager_user_id: null, amount: '100.25', currency: 'RUB', description: 'Разработка', state: 'DRAFT', status: 'DRAFT',
  paid_amount: '0.00', remaining_amount: '100.25', sent_at: null, seller: organization, buyer: {name: 'Клиент', tax_id: '', address: ''}});

beforeEach(() => {
  role = 'OWNER'; fail = false; rows = [invoice()]; organizations = [organization];
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});
    if (fail && method !== 'GET') return response({detail: 'Ошибка сохранения'}, 503);
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Студия', role, currency: 'RUB', timezone: 'UTC'}]);
    if (url.endsWith('/organizations') && method === 'GET') return response(organizations);
    if (url.endsWith('/organizations') && method === 'POST') {organizations.push({...data, id: 'o2'}); return response(organizations.at(-1), 201);}
    if (url.includes('/invoices?')) return response(rows);
    if (url.endsWith('/clients')) return response([{id: 'c1', name: 'Клиент'}]);
    if (url.includes('/deals?')) return response([]);
    if (url.includes('/projects?')) return response([]);
    if (url.endsWith('/members')) return response([]);
    if (url.endsWith('/payments') || url.endsWith('/acts')) return response([]);
    if (url.endsWith('/invoices/i1') && method === 'PATCH') {rows[0] = {...rows[0], state: data.state, status: data.state}; return response(rows[0]);}
    if (url.endsWith('/invoices/i1')) return response(rows[0]);
    if (url.endsWith('/invoices') && method === 'POST') {const row = {...invoice(), ...data, id: 'i2', number: 2}; rows.push(row); return response(row, 201);}
    throw new Error(`${method} ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});

it('loads real invoices, displays printable snapshots and issues an invoice', async () => {
  render(<Finance/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Счёт №1'}));
  const drawer = screen.getByRole('dialog', {name: 'Карточка счёта'});
  expect(within(drawer).getByRole('region', {name: 'Печатная форма счёта'}).textContent).toContain('1234567890');
  fireEvent.click(within(drawer).getByRole('button', {name: 'Выставить счёт'}));
  await waitFor(() => expect(rows[0].state).toBe('ISSUED'));
  expect(await within(drawer).findByLabelText('Сумма платежа')).toBeTruthy();
});

it('preserves the invoice draft on API failure and allows retry', async () => {
  render(<Finance/>);
  await screen.findByRole('button', {name: 'Счёт №1'});
  fireEvent.click(screen.getByRole('button', {name: 'Новый счёт'}));
  const form = screen.getByRole('dialog', {name: 'Новый счёт'});
  fireEvent.change(within(form).getByLabelText('Клиент счёта'), {target: {value: 'c1'}});
  fireEvent.change(within(form).getByLabelText('Сумма счёта'), {target: {value: '100.25'}});
  fireEvent.change(within(form).getByLabelText('Назначение счёта'), {target: {value: 'Внедрение'}});
  fail = true;
  fireEvent.click(within(form).getByRole('button', {name: 'Создать счёт'}));
  expect((await within(form).findByRole('alert')).textContent).toContain('Ошибка сохранения');
  expect((within(form).getByLabelText('Назначение счёта') as HTMLTextAreaElement).value).toBe('Внедрение');
  fail = false;
  fireEvent.click(within(form).getByRole('button', {name: 'Создать счёт'}));
  expect(await screen.findByRole('dialog', {name: 'Карточка счёта'})).toBeTruthy();
  expect(rows).toHaveLength(2);
});

it('creates organization details', async () => {
  organizations = [];
  render(<Finance/>);
  await screen.findByText('Сначала добавьте реквизиты организации. Клиенты создаются в CRM.');
  fireEvent.click(screen.getByRole('button', {name: 'Добавить организацию'}));
  const form = screen.getByRole('dialog', {name: 'Реквизиты организации'});
  fireEvent.change(within(form).getByLabelText('Название организации'), {target: {value: 'Новая студия'}});
  fireEvent.click(within(form).getByRole('button', {name: 'Сохранить организацию'}));
  await waitFor(() => expect(organizations).toHaveLength(1));
  expect(organizations[0].name).toBe('Новая студия');
});

it('does not request financial records for a manager', async () => {
  role = 'MANAGER';
  render(<Finance/>);
  expect((await screen.findByRole('alert')).textContent).toContain('только владельцу');
  expect(fetchMock.mock.calls.every(([url]) => url === '/api/v1/workspaces')).toBe(true);
});
