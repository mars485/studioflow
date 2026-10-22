import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import CRM from './CRM';
import {type Deal, type FollowUpCompletion, localDateTime} from './api';

const deal: Deal = {id: 'd1', workspace_id: 'w1', title: 'Сайт клиента', client_id: 'c1', pipeline_id: 'p1', stage_id: 's1',
  responsible_user_id: null, amount: '65000.25', currency: 'RUB', contact_name: 'Мария', source: 'Сайт', description: null,
  follow_up_at: '2026-12-01T11:30:00Z', follow_up_action: 'proposal', follow_up_comment: 'Отправить КП',
  created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z'};
let stored: Deal[];
let notes: {id: string; workspace_id: string; deal_id: string; author_user_id: string; author_name: string; body: string; kind: 'NOTE' | 'STAGE_CHANGE'; created_at: string}[];
let completed: FollowUpCompletion[];
let failMutation: boolean;
let failLoad: boolean;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  stored = [{...deal}]; notes = []; completed = []; failMutation = false; failLoad = false;
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
    if (failLoad || (method !== 'GET' && failMutation)) return response({detail: 'Server unavailable'}, 503);
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Studio', role: 'OWNER', currency: 'RUB', timezone: 'Asia/Yekaterinburg'}]);
    if (url.endsWith('/pipelines')) return response([{id: 'p1', name: 'Продажи', is_default: true, stages: [{id: 's1', name: 'Новый лид', position: 0}, {id: 's2', name: 'Контакт', position: 1}]}]);
    if (url.endsWith('/members')) return response([{id: 'm1', user_id: 'u1', email: 'manager@example.com', first_name: 'Менеджер', role: 'MANAGER'}]);
    if (url.endsWith('/clients')) return response([{id: 'c1', name: 'Клиент'}]);
    if (url.includes('/deals?')) return response(stored);
    if (url.endsWith('/follow-up/completions')) return response(completed);
    if (url.endsWith('/follow-up/complete') && method === 'POST') {
      const item: FollowUpCompletion = {id: `f${completed.length + 1}`, deal_id: 'd1', completed_by_user_id: 'u1', completed_by_name: 'Менеджер', scheduled_at: stored[0].follow_up_at!, action: stored[0].follow_up_action!, planned_comment: stored[0].follow_up_comment, outcome_comment: data.outcome_comment, completed_at: '2026-10-23T10:00:00Z'};
      completed.unshift(item); stored[0] = {...stored[0], follow_up_at: null, follow_up_action: null, follow_up_comment: null};
      return response({completion: item, deal: stored[0]}, 201);
    }
    if (url.endsWith('/activities')) {
      if (method === 'GET') return response(notes);
      const note = {id: `n${notes.length + 1}`, workspace_id: 'w1', deal_id: 'd1', author_user_id: 'u1', author_name: 'Менеджер', body: data.body, kind: 'NOTE' as const, created_at: '2026-10-23T10:00:00Z'};
      notes.unshift(note);
      return response(note, 201);
    }
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
  it('filters deals with today, overdue and missing follow-ups', async () => {
    const today = new Date(); today.setHours(12, 0, 0, 0);
    const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
    stored = [
      {...deal, id: 'today', title: 'Сегодня', follow_up_at: today.toISOString()},
      {...deal, id: 'late', title: 'Просрочено', follow_up_at: yesterday.toISOString()},
      {...deal, id: 'empty', title: 'Без дела', follow_up_at: null, follow_up_action: null, follow_up_comment: null},
    ];
    render(<CRM/>);
    await screen.findByRole('article', {name: 'Открыть Сегодня'});
    fireEvent.click(screen.getByRole('button', {name: /Follow-up сегодня/}));
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getByRole('article', {name: 'Открыть Сегодня'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: /Просрочены/}));
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getByRole('article', {name: 'Открыть Просрочено'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: /Нет дел/}));
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getByRole('article', {name: 'Открыть Без дела'})).toBeTruthy();
  });

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

  it('completes follow-up and retains its outcome after reopening', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    await screen.findByText('Завершённых действий пока нет.');
    fireEvent.change(screen.getByLabelText('Итог контакта'), {target: {value: 'Клиент согласовал предложение'}});
    fireEvent.click(screen.getByRole('button', {name: 'Отметить follow-up выполненным'}));
    await screen.findByText('Клиент согласовал предложение');
    expect(stored[0].follow_up_at).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Закрыть'}));
    fireEvent.click(screen.getByRole('article', {name: 'Открыть Сайт клиента'}));
    expect(await screen.findByText('Клиент согласовал предложение')).toBeTruthy();
  });

  it('keeps the completion outcome when the server rejects it', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    await screen.findByText('Завершённых действий пока нет.');
    failMutation = true;
    fireEvent.change(screen.getByLabelText('Итог контакта'), {target: {value: 'Повторить звонок'}});
    fireEvent.click(screen.getByRole('button', {name: 'Отметить follow-up выполненным'}));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('Итог контакта') as HTMLTextAreaElement).value).toBe('Повторить звонок');
    expect(completed).toHaveLength(0);
  });

  it('saves a deal note and reloads its history', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    await screen.findByText('Записей пока нет.');
    fireEvent.change(screen.getByLabelText('Новая заметка'), {target: {value: 'Позвонил клиенту'}});
    fireEvent.click(screen.getByRole('button', {name: 'Добавить в историю'}));
    await screen.findByText('Позвонил клиенту');
    expect(notes).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', {name: 'Закрыть'}));
    fireEvent.click(screen.getByRole('article', {name: 'Открыть Сайт клиента'}));
    expect(await screen.findByText('Позвонил клиенту')).toBeTruthy();
  });

  it('keeps a note draft when saving fails', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    await screen.findByText('Записей пока нет.');
    failMutation = true;
    fireEvent.change(screen.getByLabelText('Новая заметка'), {target: {value: 'Перезвонить завтра'}});
    fireEvent.click(screen.getByRole('button', {name: 'Добавить в историю'}));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('Новая заметка') as HTMLTextAreaElement).value).toBe('Перезвонить завтра');
    expect(notes).toHaveLength(0);
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
    fireEvent.change(screen.getByLabelText('Ответственный'), {target: {value: 'u1'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить сделку'}));
    await screen.findByRole('article', {name: 'Открыть Новый сайт'});
    expect(stored).toHaveLength(2);
    expect(stored[1].responsible_user_id).toBe('u1');
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
