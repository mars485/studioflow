import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Tasks from './Tasks';
import {type Deal, type Task, type TaskChecklistItem, type TaskStatus} from './api';

let statuses: TaskStatus[];
let tasks: Task[];
let checklist: TaskChecklistItem[];
let failMutation: boolean;

const deal: Deal = {id: 'd1', workspace_id: 'w1', title: 'Сайт клиента', client_id: 'c1', contact_id: null, pipeline_id: 'p1', stage_id: 's1',
  responsible_user_id: null, amount: '1000', currency: 'RUB', contact_name: null, source: null, description: null,
  start_date: null, end_date: null, utm_source: null, utm_medium: null, utm_campaign: null, utm_term: null, utm_content: null,
  http_referrer: null, follow_up_at: null, follow_up_action: null, follow_up_comment: null,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z'};

const makeTask = (overrides: Partial<Task>): Task => ({id: 'task1', workspace_id: 'w1', title: 'Сделать отчёт', description: null,
  status_id: 'st1', status_name: 'Сделать', is_final: false, priority: 'MEDIUM', assignee_user_id: null, creator_user_id: 'u1',
  completed_by_user_id: null, start_at: null, due_at: null, estimate_minutes: null, deal_id: null, project_id: null, contact_id: null,
  parent_task_id: null, completed_at: null, created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z',
  checklist_done: 0, checklist_total: 0, ...overrides});

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  failMutation = false;
  checklist = [];
  statuses = [{id: 'st1', name: 'Сделать', position: 0, is_final: false}, {id: 'st2', name: 'В работе', position: 1, is_final: false},
    {id: 'st3', name: 'Завершено', position: 2, is_final: true}];
  tasks = [makeTask({})];
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
    if (method !== 'GET' && failMutation) return response({detail: 'Server unavailable'}, 503);
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Studio', role: 'OWNER', currency: 'RUB', timezone: 'Asia/Yekaterinburg'}]);
    if (url.endsWith('/members')) return response([{id: 'm1', user_id: 'u1', email: 'manager@example.com', first_name: 'Менеджер', role: 'MANAGER'}]);
    if (url.includes('/deals?')) return response([deal]);
    if (url.endsWith('/time-timer')) return response(null);
    if (url.endsWith('/recurrence')) return response(null);
    if (url.includes('/time-entries?')) return response({items: [], total_seconds: 0, timezone: 'UTC', today: '2026-10-24'});
    if (url.endsWith('/task-statuses')) {
      if (method === 'POST') {const row = {id: `st${statuses.length + 1}`, name: data.name, position: statuses.length, is_final: false}; statuses.push(row); return response(row, 201);}
      return response(statuses);
    }
    if (url.includes('/task-statuses/order')) {
      statuses = data.ids.map((id: string, position: number) => ({...statuses.find(row => row.id === id)!, position}));
      return response(statuses);
    }
    if (url.includes('/task-statuses/')) {
      const id = url.split('/task-statuses/')[1];
      const row = statuses.find(item => item.id === id)!;
      if (method === 'DELETE') {
        if (tasks.some(task => task.status_id === id)) return response({detail: 'Статус с задачами удалить нельзя'}, 409);
        statuses = statuses.filter(item => item.id !== id); return response(null, 204);
      }
      Object.assign(row, data);
      if (data.name) tasks = tasks.map(task => task.status_id === id ? {...task, status_name: data.name} : task);
      return response(row);
    }
    if (/\/tasks(\?|$)/.test(url)) {
      if (method === 'POST') {
        const row = makeTask({id: `task${tasks.length + 1}`, title: data.title, description: data.description,
          priority: data.priority, status_id: data.status_id || 'st1', deal_id: data.deal_id || null,
          status_name: statuses.find(item => item.id === (data.status_id || 'st1'))?.name || 'Сделать',
          is_final: Boolean(statuses.find(item => item.id === (data.status_id || 'st1'))?.is_final)});
        tasks.push(row); return response(row, 201);
      }
      const parent = url.includes('parent_task_id=') ? url.split('parent_task_id=')[1] : null;
      if (parent) return response(tasks.filter(task => task.parent_task_id === parent));
      return response(tasks.filter(task => !task.parent_task_id));
    }
    if (url.includes('/checklist')) {
      const taskId = url.split('/tasks/')[1].split('/')[0];
      if (url.includes('/checklist/')) {
        const itemId = url.split('/checklist/')[1];
        const item = checklist.find(row => row.id === itemId)!;
        if (method === 'DELETE') {checklist = checklist.filter(row => row.id !== itemId); return response(null, 204);}
        Object.assign(item, data);
        const parentTask = tasks.find(task => task.id === taskId);
        if (parentTask) {
          parentTask.checklist_done = checklist.filter(row => row.task_id === taskId && row.is_done).length;
        }
        return response(item);
      }
      if (method === 'POST') {
        const item = {id: `c${checklist.length + 1}`, task_id: taskId, text: data.text, is_done: false, position: checklist.length, created_at: '2026-10-01T10:00:00Z'};
        checklist.push(item);
        const parentTask = tasks.find(task => task.id === taskId);
        if (parentTask) parentTask.checklist_total = checklist.filter(row => row.task_id === taskId).length;
        return response(item, 201);
      }
      return response(checklist.filter(row => row.task_id === taskId));
    }
    if (url.includes('/watchers')) {
      if (method === 'GET') return response([]);
      if (method === 'POST') return response({user_id: data.user_id, first_name: 'Менеджер', last_name: null, email: 'manager@example.com'}, 201);
      return response(null, 204);
    }
    if (url.includes('/tasks/')) {
      const id = url.split('/tasks/')[1].split('?')[0];
      const row = tasks.find(item => item.id === id)!;
      if (method === 'DELETE') {tasks = tasks.filter(item => item.id !== id); return response(null, 204);}
      if (method === 'PATCH') {
        if (data.status_id) {
          const status = statuses.find(item => item.id === data.status_id)!;
          Object.assign(row, {status_id: status.id, status_name: status.name, is_final: status.is_final});
        }
        if (data.title) row.title = data.title;
        return response(row);
      }
      return response(row);
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});

describe('task module', () => {
  it('does not silently ignore a deleted task selected from global search', async () => {
    render(<Tasks initialWorkspaceId="w1" initialTaskId="deleted"/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Задача из поиска больше недоступна');
    expect(screen.queryByRole('dialog', {name: 'Карточка задачи'})).toBeNull();
  });
  it('renders workflow columns and creates a task', async () => {
    render(<Tasks/>);
    expect(await screen.findByRole('article', {name: 'Открыть Сделать отчёт'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: 'Новая задача'}));
    const dialog = screen.getByRole('dialog', {name: 'Новая задача'});
    fireEvent.change(within(dialog).getByLabelText('Название задачи'), {target: {value: 'Подготовить прототип'}});
    fireEvent.change(within(dialog).getByLabelText('Сделка'), {target: {value: 'd1'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Создать задачу'}));
    expect(await screen.findByRole('article', {name: 'Открыть Подготовить прототип'})).toBeTruthy();
    expect(tasks).toHaveLength(2);
    expect(tasks[1].deal_id).toBe('d1');
  });

  it('adds and completes checklist items and keeps API errors visible', async () => {
    render(<Tasks/>);
    fireEvent.click(await screen.findByRole('article', {name: 'Открыть Сделать отчёт'}));
    const drawer = await screen.findByRole('dialog', {name: 'Карточка задачи'});
    fireEvent.change(within(drawer).getByLabelText('Новый пункт чек-листа'), {target: {value: 'Проверить макет'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить пункт'}));
    await waitFor(() => expect(checklist).toHaveLength(1));
    fireEvent.click(within(drawer).getByRole('checkbox', {name: 'Проверить макет'}));
    await waitFor(() => expect(checklist[0].is_done).toBe(true));
    failMutation = true;
    fireEvent.change(within(drawer).getByLabelText('Новый пункт чек-листа'), {target: {value: 'Второй'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить пункт'}));
    await within(drawer).findByRole('alert');
    expect((within(drawer).getByLabelText('Новый пункт чек-листа') as HTMLInputElement).value).toBe('Второй');
  });

  it('protects statuses in use and reorders the workflow', async () => {
    render(<Tasks/>);
    await screen.findByRole('article', {name: 'Открыть Сделать отчёт'});
    fireEvent.click(screen.getByRole('button', {name: 'Статусы'}));
    const dialog = screen.getByRole('dialog', {name: 'Статусы задач'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Удалить Сделать'}));
    expect(await within(dialog).findByRole('alert')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', {name: 'Ниже Сделать'}));
    await waitFor(() => expect(statuses[0].name).toBe('В работе'));
    fireEvent.change(within(dialog).getByLabelText('Название статуса В работе'), {target: {value: 'В работе 2'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Сохранить В работе'}));
    await waitFor(() => expect(statuses.some(row => row.name === 'В работе 2')).toBe(true));
  });
});
