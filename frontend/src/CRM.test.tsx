import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import CRM from './CRM';
import {type Client, type Contact, type Deal, type DealTask, type FollowUpCompletion, type Pipeline, type Stage, type TaskReminder, localDateTime} from './api';

const deal: Deal = {id: 'd1', workspace_id: 'w1', title: 'Сайт клиента', client_id: 'c1', contact_id: null, pipeline_id: 'p1', stage_id: 's1',
  responsible_user_id: null, amount: '65000.25', currency: 'RUB', contact_name: 'Мария', source: 'Сайт', description: null,
  start_date: null, end_date: null,
  utm_source: null, utm_medium: null, utm_campaign: null, utm_term: null, utm_content: null, http_referrer: null,
  follow_up_at: '2026-12-01T11:30:00Z', follow_up_action: 'proposal', follow_up_comment: 'Отправить КП',
  created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z'};
let stored: Deal[];
let notes: {id: string; workspace_id: string; deal_id: string; author_user_id: string; author_name: string; body: string; kind: 'NOTE' | 'STAGE_CHANGE'; created_at: string}[];
let completed: FollowUpCompletion[];
let failMutation: boolean;
let failLoad: boolean;
let fetchMock: ReturnType<typeof vi.fn>;
let stages: Stage[];
let pipelineRows: Pipeline[];
let clientRows: Client[];
let contactRows: Contact[];
let taskRows: DealTask[];
let reminderRows: TaskReminder[];
let tagRows: {id: string; name: string; created_at: string}[];
let watcherRows: {user_id: string; first_name: string; last_name: string | null; email: string}[];
let linkRows: {contact_id: string; is_primary: boolean; first_name: string; last_name: string | null; middle_name: string | null; phone: string | null; email: string | null}[];
let attachmentRows: {id: string; filename: string; content_type: string; size_bytes: number; uploaded_by_user_id: string | null; uploaded_by_name: string; created_at: string}[];
let customRows: {key: string; type: 'TEXT' | 'NUMBER' | 'DATE'; value: string}[];

beforeEach(() => {
  stored = [{...deal}]; notes = []; completed = []; taskRows = []; reminderRows = [];
  tagRows = []; watcherRows = []; linkRows = []; attachmentRows = []; customRows = []; failMutation = false; failLoad = false;
  stages = [{id: 's1', pipeline_id: 'p1', name: 'Новый лид', position: 0, stage_type: 'OPEN', color: null}, {id: 's2', pipeline_id: 'p1', name: 'Контакт', position: 1, stage_type: 'OPEN', color: null}];
  pipelineRows = [{id: 'p1', name: 'Продажи', is_default: true, is_active: true, stages}];
  clientRows = [{id: 'c1', type: 'COMPANY', name: 'Клиент', phone: null, email: null, website: null, notes: null}];
  contactRows = [];
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
    if (failLoad || (method !== 'GET' && failMutation)) return response({detail: 'Server unavailable'}, 503);
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Studio', role: 'OWNER', currency: 'RUB', timezone: 'Asia/Yekaterinburg'}]);
    if (url.endsWith('/pipelines') && method === 'POST') {const item: Pipeline = {id: 'p2', name: data.name, is_default: false, is_active: true,
      stages: [{id: 's3', pipeline_id: 'p2', name: 'Новый лид', position: 0, stage_type: 'OPEN', color: null}]}; pipelineRows.push(item); return response(item, 201);}
    if (url.endsWith('/pipelines') || url.includes('/pipelines?include_inactive=')) return response(pipelineRows.filter(row => url.includes('include_inactive=true') || row.is_active));
    if (url.includes('/pipelines/') && !url.includes('/stages')) {
      const pipelineId = url.split('/pipelines/')[1].split('/')[0];
      const row = pipelineRows.find(item => item.id === pipelineId)!;
      if (method === 'PATCH') {row.name = data.name; return response(row);}
      if (method === 'POST' && url.endsWith('/default')) {pipelineRows.forEach(item => item.is_default = item.id === pipelineId); return response(row);}
      if (method === 'POST' && url.endsWith('/deactivate')) {row.is_active = false; row.is_default = false; pipelineRows[0].is_default = true; return response(row);}
      if (method === 'POST' && url.endsWith('/activate')) {row.is_active = true; return response(row);}
      if (method === 'DELETE') {pipelineRows = pipelineRows.filter(item => item.id !== pipelineId); return response(null, 204);}
    }
    if (url.includes('/pipelines/p1/stages')) {
      if (method === 'POST') {const stage: Stage = {id: `s${stages.length + 1}`, pipeline_id: 'p1', name: data.name, position: stages.length, stage_type: data.stage_type || 'OPEN', color: data.color || null}; stages.push(stage); pipelineRows[0].stages = stages; return response(stage, 201);}
      if (method === 'PUT') {stages = data.ids.map((id: string, position: number) => ({...stages.find(stage => stage.id === id)!, position})); pipelineRows[0].stages = stages; return response(stages);}
      const id = url.split('/').at(-1);
      if (method === 'PATCH') {const index = stages.findIndex(stage => stage.id === id); stages[index] = {...stages[index], ...data}; return response(stages[index]);}
      if (method === 'DELETE') {stages = stages.filter(stage => stage.id !== id).map((stage, position) => ({...stage, position})); pipelineRows[0].stages = stages; return response(null, 204);}
    }
    if (url.endsWith('/members')) return response([{id: 'm1', user_id: 'u1', email: 'manager@example.com', first_name: 'Менеджер', role: 'MANAGER'}]);
    if (url.includes('/deals/') && url.endsWith('/tags')) {
      if (method === 'GET') return response(tagRows);
      const item = {id: `tag${tagRows.length + 1}`, name: data.name, created_at: '2026-10-23T10:00:00Z'};
      if (!tagRows.some(row => row.name.toLocaleLowerCase() === item.name.toLocaleLowerCase())) tagRows.push(item);
      return response(tagRows.find(row => row.name.toLocaleLowerCase() === item.name.toLocaleLowerCase()), 201);
    }
    if (url.includes('/deals/') && url.includes('/tags/') && method === 'DELETE') {
      tagRows = tagRows.filter(row => row.id !== url.split('/tags/')[1]); return response(null, 204);
    }
    if (url.includes('/deals/') && url.endsWith('/watchers')) {
      if (method === 'GET') return response(watcherRows);
      const item = {user_id: data.user_id, first_name: 'Менеджер', last_name: null, email: 'manager@example.com'};
      watcherRows.push(item); return response(item, 201);
    }
    if (url.includes('/deals/') && url.includes('/watchers/') && method === 'DELETE') {
      watcherRows = watcherRows.filter(row => row.user_id !== url.split('/watchers/')[1]); return response(null, 204);
    }
    if (url.includes('/deals/') && url.endsWith('/contacts')) {
      if (method === 'GET') return response(linkRows);
      const contact = contactRows.find(row => row.id === data.contact_id)!;
      const item = {contact_id: data.contact_id, is_primary: Boolean(data.is_primary), first_name: contact.first_name,
        last_name: contact.last_name, middle_name: contact.middle_name, phone: contact.phone, email: contact.email};
      linkRows.push(item); return response(item, 201);
    }
    if (url.includes('/deals/') && url.includes('/contacts/')) {
      const contactId = url.split('/contacts/')[1];
      if (method === 'DELETE') {linkRows = linkRows.filter(row => row.contact_id !== contactId); return response(null, 204);}
      linkRows = linkRows.map(row => ({...row, is_primary: row.contact_id === contactId}));
      return response(linkRows.find(row => row.contact_id === contactId));
    }
    if (url.includes('/deals/') && url.endsWith('/attachments')) {
      if (method === 'GET') return response(attachmentRows);
      const item = {id: `a${attachmentRows.length + 1}`, filename: data.filename, content_type: data.content_type,
        size_bytes: data.size_bytes, uploaded_by_user_id: 'u1', uploaded_by_name: 'Менеджер', created_at: '2026-10-23T10:00:00Z'};
      attachmentRows.unshift(item); return response(item, 201);
    }
    if (url.includes('/deals/') && url.includes('/attachments/') && method === 'DELETE') {
      attachmentRows = attachmentRows.filter(row => row.id !== url.split('/attachments/')[1]); return response(null, 204);
    }
    if (url.includes('/deals/') && url.endsWith('/custom-fields')) {
      if (method === 'PUT') customRows = [...data.values].sort((a: {key: string}, b: {key: string}) => a.key.localeCompare(b.key));
      return response({values: customRows});
    }
    if (url.endsWith('/contacts')) {
      if (method === 'POST') {const item: Contact = {id: `t${contactRows.length + 1}`, workspace_id: 'w1', first_name: data.first_name,
        last_name: data.last_name || null, middle_name: data.middle_name || null, phone: data.phone || null,
        email: data.email || null, website: data.website || null, notes: data.notes || null, client_ids: data.client_ids,
        created_at: new Date().toISOString(), updated_at: new Date().toISOString()}; contactRows.push(item); return response(item, 201);}
      return response(contactRows);
    }
    if (url.includes('/contacts/') && url.endsWith('/deals')) return response(stored.filter(item => item.contact_id === url.split('/contacts/')[1].split('/')[0]));
    if (url.includes('/contacts/')) {
      const id = url.split('/contacts/')[1].split('/')[0]; const item = contactRows.find(row => row.id === id);
      if (method === 'PATCH') {Object.assign(item!, data); return response(item);}
      if (method === 'DELETE') {contactRows = contactRows.filter(row => row.id !== id); return response(null, 204);}
      return response(item || {detail: 'Contact not found'}, item ? 200 : 404);
    }
    if (url.endsWith('/clients')) {
      if (method === 'POST') {const item: Client = {id: `c${clientRows.length + 1}`, type: 'COMPANY', name: data.name,
        phone: data.phone || null, email: data.email || null, website: data.website || null, notes: data.notes || null}; clientRows.push(item); return response(item, 201);}
      return response(clientRows);
    }
    if (url.includes('/clients/') && url.endsWith('/deals')) return response(stored.filter(item => item.client_id === url.split('/clients/')[1].split('/')[0]));
    if (url.includes('/clients/')) {
      const id = url.split('/clients/')[1].split('/')[0]; const item = clientRows.find(row => row.id === id);
      if (method === 'PATCH') {Object.assign(item!, data); return response(item);}
      if (method === 'DELETE') {clientRows = clientRows.filter(row => row.id !== id); return response(null, 204);}
      return response(item || {detail: 'Client not found'}, item ? 200 : 404);
    }
    if (url.includes('/deals?')) return response(stored);
    if (url.endsWith('/reminders/due')) return response(reminderRows.filter(item => !item.acknowledged_at && item.trigger_at && new Date(item.trigger_at) <= new Date()).map(item => ({...item, deal_id: 'd1', deal_title: 'Сайт клиента', task_title: taskRows.find(task => task.id === item.task_id)?.title || ''})));
    if (url.includes('/reminders/') && url.endsWith('/ack')) {const item = reminderRows.find(row => row.id === url.split('/reminders/')[1].split('/')[0])!; item.acknowledged_at = new Date().toISOString(); return response(item);}
    if (url.includes('/tasks/') && url.includes('/reminders')) {
      const taskId = url.split('/tasks/')[1].split('/')[0];
      if (method === 'GET') return response(reminderRows.filter(item => item.task_id === taskId));
      if (method === 'DELETE') {reminderRows = reminderRows.filter(item => item.id !== url.split('/reminders/')[1]); return response(null, 204);}
      const item: TaskReminder = {id: `r${reminderRows.length + 1}`, workspace_id: 'w1', task_id: taskId,
        recipient_user_id: data.recipient_user_id, created_by_user_id: 'u1', kind: data.kind, at: data.at,
        offset_minutes: data.offset_minutes, trigger_at: data.at, acknowledged_at: null, created_at: new Date().toISOString()};
      reminderRows.push(item); return response(item, 201);
    }
    if (url.endsWith('/my-day')) return response({tasks: taskRows.filter(item => item.assignee_user_id === 'u1' && item.status === 'OPEN').map(task => ({task, deal_title: stored.find(row => row.id === task.deal_id)?.title || ''})),
      follow_ups: stored.filter(item => item.responsible_user_id === 'u1' && item.follow_up_at).map(item => ({deal_id: item.id, deal_title: item.title, at: item.follow_up_at, action: item.follow_up_action, comment: item.follow_up_comment}))});
    if (url.endsWith('/tasks')) {
      if (method === 'GET') return response(taskRows);
      const item: DealTask = {id: `task${taskRows.length + 1}`, workspace_id: 'w1', deal_id: 'd1', title: data.title,
        description: data.description, priority: data.priority, status: 'OPEN', assignee_user_id: data.assignee_user_id,
        created_by_user_id: 'u1', completed_by_user_id: null, start_at: data.start_at, due_at: data.due_at,
        created_at: '2026-10-23T10:00:00Z', updated_at: '2026-10-23T10:00:00Z', completed_at: null};
      taskRows.push(item); return response(item, 201);
    }
    if (url.includes('/tasks/')) {
      const id = url.split('/tasks/')[1]; const item = taskRows.find(row => row.id === id)!;
      if (method === 'DELETE') {taskRows = taskRows.filter(row => row.id !== id); return response(null, 204);}
      Object.assign(item, data);
      item.completed_at = item.status === 'DONE' ? '2026-10-23T11:00:00Z' : null;
      item.completed_by_user_id = item.status === 'DONE' ? 'u1' : null;
      return response(item);
    }
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
  it('creates a contact linked to a company and selects it on the deal', async () => {
    render(<CRM/>);
    await screen.findByRole('article', {name: 'Открыть Сайт клиента'});
    fireEvent.click(screen.getByRole('button', {name: 'Компании'}));
    const companies = screen.getByRole('dialog', {name: 'Компании'});
    fireEvent.click(within(companies).getByRole('button', {name: 'Клиент'}));
    fireEvent.click(within(companies).getByRole('button', {name: 'Добавить контакт'}));
    const contacts = screen.getByRole('dialog', {name: 'Контакты'});
    fireEvent.change(within(contacts).getByLabelText('Имя'), {target: {value: 'Мария'}});
    fireEvent.change(within(contacts).getByLabelText('Фамилия'), {target: {value: 'Иванова'}});
    failMutation = true;
    fireEvent.click(within(contacts).getByRole('button', {name: 'Сохранить контакт'}));
    await within(contacts).findByRole('alert');
    expect((within(contacts).getByLabelText('Имя') as HTMLInputElement).value).toBe('Мария');
    failMutation = false;
    fireEvent.click(within(contacts).getByRole('button', {name: 'Сохранить контакт'}));
    await waitFor(() => expect(contactRows).toHaveLength(1));
    expect(contactRows[0].client_ids).toEqual(['c1']);
    fireEvent.click(within(contacts).getByRole('button', {name: 'Закрыть'}));
    fireEvent.click(screen.getByRole('article', {name: 'Открыть Сайт клиента'}));
    fireEvent.click(screen.getByRole('button', {name: 'Редактировать'}));
    fireEvent.change(screen.getByLabelText('Связанный контакт'), {target: {value: 't1'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить сделку'}));
    await waitFor(() => expect(stored[0].contact_id).toBe('t1'));
    fireEvent.click(screen.getByRole('article', {name: 'Открыть Сайт клиента'}));
    expect(screen.getByRole('button', {name: 'Иванова Мария'})).toBeTruthy();
  });
  it('opens a company from its deal and saves contact details without losing a failed draft', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    fireEvent.click(screen.getByRole('button', {name: 'Клиент'}));
    const dialog = screen.getByRole('dialog', {name: 'Компании'});
    await within(dialog).findByRole('button', {name: 'Сайт клиента'});
    fireEvent.change(within(dialog).getByLabelText('Рабочий телефон'), {target: {value: '+7 900 123-45-67'}});
    failMutation = true;
    fireEvent.click(within(dialog).getByRole('button', {name: 'Сохранить компанию'}));
    await within(dialog).findByRole('alert');
    expect((within(dialog).getByLabelText('Рабочий телефон') as HTMLInputElement).value).toBe('+7 900 123-45-67');
    failMutation = false;
    fireEvent.click(within(dialog).getByRole('button', {name: 'Сохранить компанию'}));
    await waitFor(() => expect(clientRows[0].phone).toBe('+7 900 123-45-67'));
    fireEvent.click(within(dialog).getByRole('button', {name: 'Сайт клиента'}));
    expect(await screen.findByRole('dialog', {name: 'Карточка сделки'})).toBeTruthy();
  });
  it('creates a second pipeline and keeps a draft after an API error', async () => {
    render(<CRM/>);
    await screen.findByRole('article', {name: 'Открыть Сайт клиента'});
    fireEvent.click(screen.getByRole('button', {name: 'Управление воронками'}));
    const dialog = screen.getByRole('dialog', {name: 'Управление воронками'});
    await within(dialog).findByLabelText('Новая воронка');
    fireEvent.change(within(dialog).getByLabelText('Новая воронка'), {target: {value: 'Сопровождение'}});
    failMutation = true;
    fireEvent.click(within(dialog).getByRole('button', {name: 'Создать воронку'}));
    await within(dialog).findByRole('alert');
    expect((within(dialog).getByLabelText('Новая воронка') as HTMLInputElement).value).toBe('Сопровождение');
    failMutation = false;
    fireEvent.click(within(dialog).getByRole('button', {name: 'Создать воронку'}));
    await waitFor(() => expect(pipelineRows).toHaveLength(2));
    await waitFor(() => expect((screen.getByRole('combobox', {name: 'Воронка'}) as HTMLSelectElement).value).toBe('p2'));
    fireEvent.click(within(dialog).getByRole('button', {name: 'Отключить Сопровождение'}));
    await waitFor(() => expect((screen.getByRole('combobox', {name: 'Воронка'}) as HTMLSelectElement).value).toBe('p1'));
    expect(screen.getByRole('article', {name: 'Открыть Сайт клиента'})).toBeTruthy();
  });
  it('lets an owner add and reorder stages while preserving the draft on failure', async () => {
    render(<CRM/>);
    await screen.findByRole('article', {name: 'Открыть Сайт клиента'});
    fireEvent.click(screen.getByRole('button', {name: 'Настроить стадии'}));
    const dialog = screen.getByRole('dialog', {name: 'Настройка стадий'});
    fireEvent.change(within(dialog).getByLabelText('Новый этап'), {target: {value: 'Переговоры'}});
    failMutation = true;
    fireEvent.click(within(dialog).getByRole('button', {name: 'Добавить этап'}));
    await within(dialog).findByRole('alert');
    expect((within(dialog).getByLabelText('Новый этап') as HTMLInputElement).value).toBe('Переговоры');
    failMutation = false;
    fireEvent.click(within(dialog).getByRole('button', {name: 'Добавить этап'}));
    await waitFor(() => expect(stages).toHaveLength(3));
    await within(dialog).findByRole('button', {name: 'Выше Переговоры'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Выше Переговоры'}));
    await waitFor(() => expect(stages[1].name).toBe('Переговоры'));
    expect(screen.getByText('Переговоры', {selector: '.colHead b'})).toBeTruthy();
  });
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

  it('saves deal dates and shows them in the card', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    fireEvent.click(screen.getByRole('button', {name: 'Редактировать'}));
    fireEvent.change(screen.getByLabelText('Начало сделки'), {target: {value: '2026-10-23'}});
    fireEvent.change(screen.getByLabelText('Окончание сделки'), {target: {value: '2026-11-02'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить сделку'}));
    await waitFor(() => expect(stored[0].start_date).toBe('2026-10-23'));
    expect(stored[0].end_date).toBe('2026-11-02');
    expect(screen.getByText('Сроки: 2026-10-23 — 2026-11-02')).toBeTruthy();
  });

  it('creates, edits and completes a task linked to the deal', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    await screen.findByText('Задач по сделке пока нет.');
    fireEvent.change(screen.getByLabelText('Название задачи'), {target: {value: 'Подготовить ТЗ'}});
    fireEvent.change(screen.getByLabelText('Исполнитель задачи'), {target: {value: 'u1'}});
    fireEvent.change(screen.getByLabelText('Крайний срок'), {target: {value: '2026-12-03T18:00'}});
    fireEvent.click(screen.getByRole('button', {name: 'Добавить задачу'}));
    await screen.findByText('Подготовить ТЗ');
    expect(taskRows[0].assignee_user_id).toBe('u1');
    expect(taskRows[0].due_at).toBe(new Date('2026-12-03T18:00').toISOString());
    fireEvent.click(screen.getByRole('button', {name: 'Изменить Подготовить ТЗ'}));
    fireEvent.change(screen.getByLabelText('Название задачи'), {target: {value: 'Подготовить и проверить ТЗ'}});
    fireEvent.click(screen.getByRole('button', {name: 'Сохранить задачу'}));
    await screen.findByText('Подготовить и проверить ТЗ');
    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(() => expect(taskRows[0].status).toBe('DONE'));
    fireEvent.click(screen.getByRole('button', {name: 'Закрыть'}));
    fireEvent.click(screen.getByRole('article', {name: 'Открыть Сайт клиента'}));
    expect(await screen.findByText('Подготовить и проверить ТЗ')).toBeTruthy();
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
  });

  it('shows assigned tasks and follow-ups in My Day and completes a task', async () => {
    stored[0].responsible_user_id = 'u1';
    taskRows = [{id: 'task1', workspace_id: 'w1', deal_id: 'd1', title: 'Позвонить клиенту', description: null,
      priority: 'HIGH', status: 'OPEN', assignee_user_id: 'u1', created_by_user_id: 'u1', completed_by_user_id: null,
      start_at: null, due_at: '2026-12-02T18:00:00Z', created_at: '2026-10-23T10:00:00Z', updated_at: '2026-10-23T10:00:00Z', completed_at: null}];
    render(<CRM/>);
    await screen.findByRole('article', {name: 'Открыть Сайт клиента'});
    fireEvent.click(screen.getByRole('button', {name: 'Мой день'}));
    const panel = await screen.findByRole('region', {name: 'Мой день'});
    expect(within(panel).getByText('Позвонить клиенту')).toBeTruthy();
    expect(within(panel).getByText(/Следующий контакт/)).toBeTruthy();
    fireEvent.click(within(panel).getByRole('button', {name: 'Выполнено'}));
    await waitFor(() => expect(taskRows[0].status).toBe('DONE'));
    expect(within(panel).queryByText('Позвонить клиенту')).toBeNull();
  });

  it('creates a task reminder and acknowledges it in My Day', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    fireEvent.change(screen.getByLabelText('Название задачи'), {target: {value: 'Позвонить завтра'}});
    fireEvent.click(screen.getByRole('button', {name: 'Добавить задачу'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Напоминания: Позвонить завтра'}));
    fireEvent.change(screen.getByLabelText('Дата и время напоминания'), {target: {value: '2020-01-01T10:00'}});
    fireEvent.click(screen.getByRole('button', {name: 'Добавить напоминание'}));
    await waitFor(() => expect(reminderRows).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', {name: 'Закрыть'}));
    fireEvent.click(screen.getByRole('button', {name: 'Мой день'}));
    const panel = await screen.findByRole('region', {name: 'Мой день'});
    await within(panel).findByText('Напоминания');
    fireEvent.click(within(panel).getByRole('button', {name: 'Прочитано'}));
    await waitFor(() => expect(reminderRows[0].acknowledged_at).not.toBeNull());
    expect(within(panel).queryByText('Напоминания')).toBeNull();
  });

  it('manages tags, watchers and linked contacts in the deal card', async () => {
    contactRows = [{id: 't1', workspace_id: 'w1', first_name: 'Мария', last_name: 'Иванова', middle_name: null, phone: '+7 900',
      email: null, website: null, notes: null, client_ids: ['c1'], created_at: '2026-10-23T10:00:00Z', updated_at: '2026-10-23T10:00:00Z'}];
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    const drawer = await screen.findByRole('dialog', {name: 'Карточка сделки'});
    await within(drawer).findByText('Тегов пока нет.');
    fireEvent.change(within(drawer).getByLabelText('Новый тег'), {target: {value: 'важное'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить тег'}));
    await waitFor(() => expect(tagRows).toHaveLength(1));
    expect(within(drawer).getByRole('button', {name: 'Убрать тег важное'})).toBeTruthy();
    fireEvent.change(within(drawer).getByLabelText('Новый наблюдатель'), {target: {value: 'u1'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить наблюдателя'}));
    await waitFor(() => expect(watcherRows).toHaveLength(1));
    const watcherList = within(drawer).getByRole('list', {name: 'Наблюдатели сделки'});
    expect(within(watcherList).getByText(/Менеджер · manager@example.com/)).toBeTruthy();
    fireEvent.change(within(drawer).getByLabelText('Новый контакт сделки'), {target: {value: 't1'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Связать контакт'}));
    await waitFor(() => expect(linkRows).toHaveLength(1));
    fireEvent.click(within(drawer).getByRole('button', {name: 'Сделать основным'}));
    await waitFor(() => expect(linkRows[0].is_primary).toBe(true));
    expect(within(drawer).getByText('Основной')).toBeTruthy();
    fireEvent.click(within(drawer).getByRole('button', {name: 'Убрать наблюдателя Менеджер'}));
    await waitFor(() => expect(watcherRows).toHaveLength(0));
    fireEvent.click(within(drawer).getByRole('button', {name: 'Убрать тег важное'}));
    await waitFor(() => expect(tagRows).toHaveLength(0));
  });

  it('saves UTM marks and custom fields and reports API errors', async () => {
    render(<CRM/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сайт клиента'}));
    const drawer = await screen.findByRole('dialog', {name: 'Карточка сделки'});
    fireEvent.change(within(drawer).getByLabelText('utm_source'), {target: {value: 'yandex'}});
    fireEvent.change(within(drawer).getByLabelText('http_referrer'), {target: {value: 'https://example.com'}});
    failMutation = true;
    fireEvent.click(within(drawer).getByRole('button', {name: 'Сохранить UTM-метки'}));
    await within(drawer).findByRole('alert');
    expect((within(drawer).getByLabelText('utm_source') as HTMLInputElement).value).toBe('yandex');
    failMutation = false;
    fireEvent.click(within(drawer).getByRole('button', {name: 'Сохранить UTM-метки'}));
    await waitFor(() => expect(stored[0].utm_source).toBe('yandex'));
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить поле'}));
    fireEvent.change(within(drawer).getByLabelText('Ключ поля 1'), {target: {value: 'Бюджет'}});
    fireEvent.change(within(drawer).getByLabelText('Тип поля 1'), {target: {value: 'NUMBER'}});
    fireEvent.change(within(drawer).getByLabelText('Значение поля 1'), {target: {value: '120000.50'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Сохранить поля'}));
    await waitFor(() => expect(customRows).toHaveLength(1));
    expect(customRows[0]).toEqual({key: 'Бюджет', type: 'NUMBER', value: '120000.50'});
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
