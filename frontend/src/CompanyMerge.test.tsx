import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import CompanyMerge from './CompanyMerge';
import ClientMergeHistory from './ClientMergeHistory';

const source = {id: 'c2', name: 'Дубль', type: 'COMPANY', phone: '+7 900', email: 'duplicate@example.com', website: null, notes: 'Старая заметка'};
const target = {...source, id: 'c1', name: 'Основная', phone: null, notes: null};
const preview = {source, target, preview_version: 'a'.repeat(64), counts: {deals: {source: 2, target: 1}, contacts: {source: 1, target: 0}}};
const receipt = {id: 'm1', request_key: 'key', source_id: 'c2', target_id: 'c1', actor_name: 'Администратор',
  created_at: '2026-10-26T12:00:00Z', source_fields: ['phone'], snapshot: {source, target, references: {deals: {source: ['d1', 'd2'], target: ['d3']}}}};
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

async function confirm() {
  fireEvent.click(await screen.findByRole('checkbox', {name: /Я проверил компании/}));
}

it('requires explicit confirmation and submits chosen fields only once while pending', async () => {
  let finish: (value: Response) => void = () => {};
  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => url.endsWith('/preview') ? response(preview) : new Promise<Response>(resolve => {finish = resolve;}));
  vi.stubGlobal('fetch', fetchMock);
  const onMerged = vi.fn(async () => {});
  render(<CompanyMerge base="/workspaces/w1" sourceId="c2" targetId="c1" onClose={vi.fn()} onMerged={onMerged}/>);
  const submit = await screen.findByRole('button', {name: 'Подтвердить слияние'});
  expect((submit as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox', {name: 'Взять из исходной: Телефон'}));
  await confirm(); fireEvent.click(submit); fireEvent.click(submit);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const options = fetchMock.mock.calls[1][1] as RequestInit;
  expect(JSON.parse(String(options.body))).toMatchObject({source_id: 'c2', target_id: 'c1', source_fields: ['phone'], confirmed: true});
  expect((screen.getByRole('button', {name: 'Закрыть слияние'}) as HTMLButtonElement).disabled).toBe(true);
  finish(response(receipt));
  expect(await screen.findByText(/Компании объединены/)).toBeTruthy();
  expect(onMerged).toHaveBeenCalledWith(receipt);
  expect(screen.getByText('Старая заметка')).toBeTruthy();
});

it('retains an uncertain operation and retries with the same idempotency key and fields', async () => {
  let fail = true;
  const bodies: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
    if (url.endsWith('/preview')) return response(preview);
    bodies.push(String(options.body));
    if (fail) throw new Error('Потеря соединения');
    return response(receipt);
  }));
  render(<CompanyMerge base="/workspaces/w1" sourceId="c2" targetId="c1" onClose={vi.fn()} onMerged={vi.fn(async () => {})}/>);
  fireEvent.click(await screen.findByRole('checkbox', {name: 'Взять из исходной: Телефон'}));
  await confirm(); fireEvent.click(screen.getByRole('button', {name: 'Подтвердить слияние'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Потеря соединения');
  expect((screen.getByRole('checkbox', {name: 'Взять из исходной: Телефон'}) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole('button', {name: 'Обновить предпросмотр'}) as HTMLButtonElement).disabled).toBe(true);
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Повторить слияние'}));
  await screen.findByText(/Компании объединены/);
  expect(bodies[0]).toBe(bodies[1]);
});

it('requires a new preview and confirmation after a conflict', async () => {
  let previews = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/preview') ? (previews++, response(preview)) : response({detail: 'Карточки изменились'}, 409)));
  render(<CompanyMerge base="/workspaces/w1" sourceId="c2" targetId="c1" onClose={vi.fn()} onMerged={vi.fn(async () => {})}/>);
  await confirm(); fireEvent.click(screen.getByRole('button', {name: 'Подтвердить слияние'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Карточки изменились');
  expect((screen.getByRole('button', {name: 'Подтвердить слияние'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'Обновить предпросмотр'}));
  await screen.findByRole('checkbox', {name: /Я проверил компании/});
  expect(previews).toBe(2);
  expect((screen.getByRole('checkbox', {name: /Я проверил компании/}) as HTMLInputElement).checked).toBe(false);
});

it('does not repeat a completed merge when refreshing the directory fails', async () => {
  const fetchMock = vi.fn(async (url: string) => response(url.endsWith('/preview') ? preview : receipt));
  vi.stubGlobal('fetch', fetchMock);
  const onMerged = vi.fn().mockRejectedValueOnce(new Error('Каталог недоступен')).mockResolvedValue(undefined);
  render(<CompanyMerge base="/workspaces/w1" sourceId="c2" targetId="c1" onClose={vi.fn()} onMerged={onMerged}/>);
  await confirm(); fireEvent.click(screen.getByRole('button', {name: 'Подтвердить слияние'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Слияние уже выполнено');
  fireEvent.click(screen.getByRole('button', {name: 'Обновить каталог после слияния'}));
  await waitFor(() => expect(onMerged).toHaveBeenCalledTimes(2));
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole('button', {name: 'Подтвердить слияние'})).toBeNull();
});

it('shows a deleted company error and allows retrying preview without mutation', async () => {
  let fail = true;
  vi.stubGlobal('fetch', vi.fn(async () => fail ? response({detail: 'Компания не найдена'}, 404) : response(preview)));
  render(<CompanyMerge base="/workspaces/w1" sourceId="c2" targetId="c1" onClose={vi.fn()} onMerged={vi.fn(async () => {})}/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Компания не найдена');
  expect(screen.queryByRole('button', {name: 'Подтвердить слияние'})).toBeNull();
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Обновить предпросмотр'}));
  expect(await screen.findByRole('button', {name: 'Подтвердить слияние'})).toBeTruthy();
});

it('loads historical profiles on demand after remount and handles read failure', async () => {
  let fail = true;
  const fetchMock = vi.fn(async () => fail ? response({detail: 'Журнал недоступен'}, 503) : response([receipt]));
  vi.stubGlobal('fetch', fetchMock);
  render(<ClientMergeHistory base="/workspaces/w1" targetId="c1"/>);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'История слияний'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Журнал недоступен');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Повторить загрузку истории'}));
  expect(await screen.findByText(/Квитанция слияния/)).toBeTruthy();
  expect(screen.getByText('Старая заметка')).toBeTruthy();
});

it('unlocks preview refresh after a company was removed before confirmation', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/preview') ? response(preview) : response({detail: 'Компания не найдена'}, 404)));
  render(<CompanyMerge base="/workspaces/w1" sourceId="c2" targetId="c1" onClose={vi.fn()} onMerged={vi.fn(async () => {})}/>);
  await confirm(); fireEvent.click(screen.getByRole('button', {name: 'Подтвердить слияние'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Компания не найдена');
  expect((screen.getByRole('button', {name: 'Обновить предпросмотр'}) as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole('button', {name: 'Подтвердить слияние'}) as HTMLButtonElement).disabled).toBe(true);
});

it('previews and merges contacts with person fields and the contact endpoint', async () => {
  const contactSource = {id: 'p2', first_name: 'Анна', last_name: 'Исходная', middle_name: null,
    phone: '123456789', email: null, website: null, notes: 'Исходная заметка контакта'};
  const contactTarget = {...contactSource, id: 'p1', first_name: 'Мария', last_name: 'Основная', phone: null};
  const contactPreview = {source: contactSource, target: contactTarget, preview_version: 'b'.repeat(64),
    counts: {companies: {source: 2, target: 1}, primary_deals: {source: 1, target: 1}, tasks: {source: 1, target: 0}}};
  const contactReceipt = {...receipt, source_id: 'p2', target_id: 'p1', source_fields: ['first_name', 'phone'],
    snapshot: {source: contactSource, target: contactTarget, references: {tasks: {source: ['t1'], target: []}}}};
  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => response(url.endsWith('/preview') ? contactPreview : contactReceipt));
  vi.stubGlobal('fetch', fetchMock);
  render(<CompanyMerge base="/workspaces/w1" sourceId="p2" targetId="p1" kind="contact" onClose={vi.fn()} onMerged={vi.fn(async () => {})}/>);
  expect(await screen.findByText('Останется: Основная Мария')).toBeTruthy();
  expect(screen.queryByRole('checkbox', {name: 'Взять из исходной: Название'})).toBeNull();
  fireEvent.click(screen.getByRole('checkbox', {name: 'Взять из исходной: Имя'}));
  fireEvent.click(screen.getByRole('checkbox', {name: 'Взять из исходной: Телефон'}));
  fireEvent.click(screen.getByRole('checkbox', {name: /Я проверил контакты/}));
  fireEvent.click(screen.getByRole('button', {name: 'Подтвердить слияние'}));
  await screen.findByText(/Контакты объединены/);
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/workspaces/w1/contact-merges/preview');
  expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/workspaces/w1/contact-merges');
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).source_fields).toEqual(['first_name', 'phone']);
});

it('loads contact history without calling the company history endpoint', async () => {
  const fetchMock = vi.fn(async (_url: string) => response([]));
  vi.stubGlobal('fetch', fetchMock);
  render(<ClientMergeHistory base="/workspaces/w1" targetId="p1" kind="contact"/>);
  fireEvent.click(screen.getByRole('button', {name: 'История слияний'}));
  await screen.findByText('Слияний на этой странице нет.');
  expect(fetchMock.mock.calls[0][0]).toContain('/contact-merges?target_id=p1');
});
