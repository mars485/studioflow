import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import CRM from './CRM';
import {type Deal, localDateTime} from './api';

const deal: Deal = {id: 'd1', workspace_id: 'w1', title: 'Сайт клиента', client_id: 'c1', pipeline_id: 'p1', stage_id: 's1',
  amount: '65000.25', currency: 'RUB', contact_name: 'Мария', source: 'Сайт', description: null,
  follow_up_at: '2026-12-01T11:30:00Z', follow_up_action: 'proposal', follow_up_comment: 'Отправить КП',
  created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z'};
let stored: Deal[];
let failMutation: boolean;
let failLoad: boolean;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  stored = [{...deal}]; failMutation = false; failLoad = false;
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
    if (failLoad || (method !== 'GET' && failMutation)) return response({detail: 'Server unavailable'}, 503);
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Studio', currency: 'RUB', timezone: 'Asia/Yekaterinburg'}]);
    if (url.endsWith('/pipelines')) return response([{id: 'p1', name: 'Продажи', is_default: true, stages: [{id: 's1', name: 'Новый лид', position: 0}, {id: 's2', name: 'Контакт', position: 1}]}]);
    if (url.endsWith('/clients')) return response([{id: 'c1', name: 'Клиент'}]);
    if (url.includes('/deals?')) return response(stored);
    if (url.endsWith('/follow-up')) {
      stored[0] = {...stored[0], follow_up_at: data?.at || null, follow_up_action: data?.action || null, follow_up_comment: data?.comment || null};
      return response(stored[0]);
    }
    if (method === 'PATCH') {stored[0] = {...stored[0], ...data}; return response(stored[0]);}
    if (method === 'POST') {const created = {...deal, ...data, id: 'd2'}; stored.push(created); return response(created, 201);}
    if (method === 'DELETE') {stored = []; return response(null, 204);}
    throw new Error(`Unexpected request: ${method} ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});

describe('CRM persistence', () => {
  it('loads from the API and keeps a card in place when drag-and-drop fails', async () => {
    render(<CRM/>);
    expect(screen.getByRole('status').textContent).toContain('Загрузка');
    const card = await screen.findByRole('article', {name: 'Открыть Сайт клиента'});
    const target = screen.getByText('Контакт', {selector: '.colHead b'}).closest('section')!;
    failMutation = true;
    fireEvent.drop(target, {dataTransfer: {getData: () => 'd1'}});
    await screen.findByRole('alert');
    expect(card.closest('section')?.textContent).toContain('Новый лид');
    failMutation = false;
    fireEvent.drop(target, {dataTransfer: {getData: () => 'd1'}});
    await waitFor(() => expect(target.contains(screen.getByRole('article', {name: 'Открыть Сайт клиента'}))).toBe(true));
    expect(stored[0].stage_id).toBe('s2');
  });

  it('saves follow-up and restores it on reopening the drawer', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    fireEvent.change(screen.getByLabelText('Дата и время'), {target: {value: '2026-12-02T15:45'}});
    fireEvent.change(screen.getByLabelText('Что сделать'), {target: {value: 'call'}});
    fireEvent.change(screen.getByLabelText('Комментарий'), {target: {value: 'Обсудить договор'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить follow-up'}));
    await screen.findByText('Follow-up сохранён');
    expect(stored[0].follow_up_at).toBe(new Date('2026-12-02T15:45').toISOString());
    fireEvent.click(screen.getByRole('button', {name: 'Закрыть'}));
    fireEvent.click(screen.getByRole('article', {name: 'Открыть Сайт клиента'}));
    expect((screen.getByLabelText('Комментарий') as HTMLTextAreaElement).value).toBe('Обсудить договор');
    expect((screen.getByLabelText('Дата и время') as HTMLInputElement).value).toBe(localDateTime(stored[0].follow_up_at));
  });

  it('keeps the follow-up draft when the server rejects a save', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    failMutation = true;
    fireEvent.change(screen.getByLabelText('Комментарий'), {target: {value: 'Сохранить черновик'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить follow-up'}));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('Комментарий') as HTMLTextAreaElement).value).toBe('Сохранить черновик');
    expect(stored[0].follow_up_comment).toBe('Отправить КП');
  });

  it('creates and edits a deal through the API', async () => {
    render(<CRM/>);
    await screen.findByRole('article', {name: 'Открыть Сайт клиента'});
    fireEvent.click(screen.getByRole('button', {name: 'Новая сделка'}));
    fireEvent.change(screen.getByLabelText('Название сделки'), {target: {value: 'Новый сайт'}});
    fireEvent.change(screen.getByLabelText('Компания / клиент'), {target: {value: 'c1'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить сделку'}));
    await screen.findByRole('article', {name: 'Открыть Новый сайт'});
    expect(stored).toHaveLength(2);
    fireEvent.click(screen.getByRole('article', {name: 'Открыть Сайт клиента'}));
    fireEvent.click(screen.getByRole('button', {name: 'Редактировать'}));
    fireEvent.change(screen.getByLabelText('Название сделки'), {target: {value: 'Обновлённый сайт'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить сделку'}));
    await screen.findByRole('article', {name: 'Открыть Обновлённый сайт'});
    expect(stored[0].title).toBe('Обновлённый сайт');
  });

  it('deletes a deal and displays an empty state', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    fireEvent.click(screen.getByRole('button', {name: /^Удалить$/}));
    await screen.findByText('Пока нет сделок. Создайте первую сделку.');
    expect(stored).toHaveLength(0);
  });

  it('offers retry after a failed initial load', async () => {
    failLoad = true;
    render(<CRM/>);
    const alert = await screen.findByRole('alert');
    expect(screen.queryAllByRole('article')).toHaveLength(0);
    failLoad = false;
    fireEvent.click(within(alert).getByRole('button', {name: 'Повторить загрузку'}));
    await screen.findByRole('article', {name: 'Открыть Сайт клиента'});
  });
});
