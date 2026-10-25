import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Projects from './Projects';
import {type Project, type ProjectEvent, type ProjectMember, type ProjectStage, type Task, type TaskStatus} from './api';
import type {ProjectTemplate} from './projectTemplateTypes';

let projects: Project[];
let stages: ProjectStage[];
let statuses: TaskStatus[];
let projectMembers: ProjectMember[];
let events: ProjectEvent[];
let projectTasks: Task[];
let failMutation: boolean;
let templateRows: ProjectTemplate[];

const baseProject = (overrides: Partial<Project> = {}): Project => ({id: 'pr1', workspace_id: 'w1', title: 'Внедрение CRM',
  client_id: 'c1', deal_id: 'd1', stage_id: 'ps1', stage_name: 'Подготовка', manager_user_id: null,
  amount: '65000.25', currency: 'RUB', start_date: null, end_date: null, status: 'ACTIVE', archived_at: null,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z', tasks_total: 0, tasks_done: 0, members_count: 0, ...overrides});

const baseTask = (overrides: Partial<Task> = {}): Task => ({id: 't1', workspace_id: 'w1', title: 'Смета', description: null,
  status_id: 'st1', status_name: 'Сделать', is_final: false, priority: 'MEDIUM', assignee_user_id: null, creator_user_id: 'u1',
  completed_by_user_id: null, start_at: null, due_at: null, estimate_minutes: null, deal_id: null, project_id: 'pr1',
  contact_id: null, parent_task_id: null, completed_at: null, created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z',
  checklist_done: 0, checklist_total: 0, ...overrides});

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  failMutation = false;
  templateRows = [];
  stages = [{id: 'ps1', name: 'Подготовка', position: 0}, {id: 'ps2', name: 'В работе', position: 1}];
  statuses = [{id: 'st1', name: 'Сделать', position: 0, is_final: false}, {id: 'st2', name: 'Завершено', position: 1, is_final: true}];
  projects = [baseProject()];
  projectMembers = [];
  events = [{id: 'e1', kind: 'CREATED', body: 'Проект создан из сделки «Сайт»', author_name: 'Менеджер', created_at: '2026-10-01T10:00:00Z'}];
  projectTasks = [];
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
    if (method !== 'GET' && failMutation) return response({detail: 'Server unavailable'}, 503);
    if (url === '/api/v1/workspaces') return response([{id: 'w1', name: 'Studio', role: 'OWNER', currency: 'RUB', timezone: 'Asia/Yekaterinburg'}]);
    if (url.endsWith('/project-stages')) return response(stages);
    if (url.endsWith('/project-templates')) return response(templateRows);
    if (url.endsWith('/task-statuses')) return response(statuses);
    if (url === '/api/v1/workspaces/w1/members') return response([{id: 'm1', user_id: 'u1', email: 'manager@example.com', first_name: 'Менеджер', role: 'MANAGER'}]);
    if (url.endsWith('/clients')) return response([{id: 'c1', type: 'COMPANY', name: 'Клиент', phone: null, email: null, website: null, notes: null}]);
    if (url.includes('/deals?limit=')) return response([{id: 'd1', workspace_id: 'w1', title: 'Сайт клиента', client_id: 'c1', contact_id: null,
      pipeline_id: 'p1', stage_id: 's1', responsible_user_id: null, amount: '65000.25', currency: 'RUB', contact_name: null, source: null,
      description: null, start_date: null, end_date: null, utm_source: null, utm_medium: null, utm_campaign: null, utm_term: null,
      utm_content: null, http_referrer: null, follow_up_at: null, follow_up_action: null, follow_up_comment: null,
      created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z'}]);
    if (url.includes('/tasks?project_id=')) return response(projectTasks);
    if (url.includes('/tasks') && method === 'POST') {
      const row = baseTask({id: `t${projectTasks.length + 1}`, title: data.title, project_id: data.project_id});
      projectTasks.push(row);
      projects[0] = {...projects[0], tasks_total: projectTasks.length};
      return response(row, 201);
    }
    if (url.includes('/projects/') && url.endsWith('/members')) {
      if (method === 'GET') return response(projectMembers);
      const row: ProjectMember = {user_id: data.user_id, first_name: 'Менеджер', last_name: null, email: 'manager@example.com', role: 'MEMBER'};
      projectMembers.push(row);
      return response(row, 201);
    }
    if (url.includes('/projects/') && url.includes('/members/') && method === 'DELETE') {
      projectMembers = projectMembers.filter(row => row.user_id !== url.split('/members/')[1]);
      return response(null, 204);
    }
    if (url.includes('/projects/') && url.endsWith('/events')) {
      if (method === 'GET') return response(events);
      const row = {id: `e${events.length + 1}`, kind: 'NOTE', body: data.body, author_name: 'Менеджер', created_at: '2026-10-02T10:00:00Z'};
      events.unshift(row); return response(row, 201);
    }
    if (url.includes('/projects/') && url.endsWith('/contacts')) return response([]);
    if (url.includes('/projects/') && method === 'PATCH') {
      const id = url.split('/projects/')[1];
      projects = projects.map(project => project.id === id ? {...project, ...data,
        stage_name: data.stage_id ? stages.find(stage => stage.id === data.stage_id)!.name : project.stage_name,
        archived_at: data.status === 'ARCHIVED' ? '2026-10-03T10:00:00Z' : null} : project);
      return response(projects.find(project => project.id === id));
    }
    if (url.endsWith('/projects?status=all')) return response(projects);
    if (url.endsWith('/projects') && method === 'POST') {
      const row = baseProject({id: `pr${projects.length + 1}`, title: data.title || 'Из сделки', client_id: data.client_id || 'c1',
        deal_id: data.deal_id || null, amount: '0'});
      projects = [row, ...projects];
      return response(row, 201);
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});

describe('projects', () => {
  it('reports an unavailable project selected from global search', async () => {
    render(<Projects initialWorkspaceId="w1" initialProjectId="deleted"/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Проект из поиска больше недоступен');
    expect(screen.queryByRole('dialog', {name: 'Карточка проекта'})).toBeNull();
  });
  it('selects a template and submits its start date when creating a project', async () => {
    templateRows = [{id: 'tpl1', name: 'Типовой сайт', description: null, phases: [{title: 'Дизайн', start_offset: 0, end_offset: 5}],
      source_project_title: 'Источник', created_by_name: 'Tester', created_at: '2026-10-24T10:00:00Z'}];
    render(<Projects/>);
    await screen.findByRole('button', {name: 'Внедрение CRM'});
    fireEvent.click(screen.getByRole('button', {name: 'Новый проект'}));
    const dialog = screen.getByRole('dialog', {name: 'Новый проект'});
    fireEvent.change(within(dialog).getByLabelText('Название проекта'), {target: {value: 'По шаблону'}});
    fireEvent.change(within(dialog).getByLabelText('Клиент проекта'), {target: {value: 'c1'}});
    fireEvent.change(within(dialog).getByLabelText('Шаблон проекта'), {target: {value: 'tpl1'}});
    fireEvent.change(within(dialog).getByLabelText('Начало проекта по шаблону'), {target: {value: '2027-01-15'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Создать проект'}));
    await screen.findByRole('button', {name: 'По шаблону'});
    const call = fetchMock.mock.calls.find(([url, options]) => url.endsWith('/projects') && options.method === 'POST')!;
    expect(JSON.parse(String(call[1].body))).toMatchObject({template_id: 'tpl1', start_date: '2027-01-15'});
  });
  it('lists projects, filters by tab and creates a manual project', async () => {
    render(<Projects/>);
    expect(await screen.findByRole('button', {name: 'Внедрение CRM'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: 'Новый проект'}));
    const dialog = screen.getByRole('dialog', {name: 'Новый проект'});
    fireEvent.change(within(dialog).getByLabelText('Название проекта'), {target: {value: 'Новый сайт'}});
    fireEvent.change(within(dialog).getByLabelText('Клиент проекта'), {target: {value: 'c1'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Создать проект'}));
    expect(await screen.findByRole('button', {name: 'Новый сайт'})).toBeTruthy();
    expect(projects).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', {name: 'Архив'}));
    await waitFor(() => expect(screen.queryByRole('button', {name: 'Новый сайт'})).toBeNull());
  });

  it('adds project members, tasks and events and archives the project', async () => {
    render(<Projects/>);
    fireEvent.click(await screen.findByRole('button', {name: 'Внедрение CRM'}));
    const drawer = await screen.findByRole('dialog', {name: 'Карточка проекта'});
    fireEvent.click(within(drawer).getByRole('tab', {name: /Команда/}));
    fireEvent.change(within(drawer).getByLabelText('Новый участник'), {target: {value: 'u1'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить участника'}));
    await waitFor(() => expect(projectMembers).toHaveLength(1));
    fireEvent.click(within(drawer).getByRole('tab', {name: /Задачи/}));
    fireEvent.change(within(drawer).getByLabelText('Новая задача проекта'), {target: {value: 'Согласовать смету'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить задачу'}));
    await waitFor(() => expect(projectTasks).toHaveLength(1));
    fireEvent.click(within(drawer).getByRole('tab', {name: 'События'}));
    fireEvent.change(within(drawer).getByLabelText('Новая запись'), {target: {value: 'Созвон с клиентом'}});
    fireEvent.click(within(drawer).getByRole('button', {name: 'Добавить запись'}));
    await waitFor(() => expect(events[0].body).toBe('Созвон с клиентом'));
    fireEvent.click(within(drawer).getByRole('tab', {name: 'Общие'}));
    fireEvent.click(within(drawer).getByRole('button', {name: 'В архив'}));
    await waitFor(() => expect(projects[0].status).toBe('ARCHIVED'));
    expect(within(drawer).getByRole('button', {name: 'Вернуть из архива'})).toBeTruthy();
  });

  it('keeps an API error visible when creating a project fails', async () => {
    render(<Projects/>);
    await screen.findByRole('button', {name: 'Внедрение CRM'});
    fireEvent.click(screen.getByRole('button', {name: 'Новый проект'}));
    const dialog = screen.getByRole('dialog', {name: 'Новый проект'});
    fireEvent.change(within(dialog).getByLabelText('Название проекта'), {target: {value: 'Проблемный'}});
    fireEvent.change(within(dialog).getByLabelText('Клиент проекта'), {target: {value: 'c1'}});
    failMutation = true;
    fireEvent.click(within(dialog).getByRole('button', {name: 'Создать проект'}));
    expect(await within(dialog).findByRole('alert')).toBeTruthy();
    expect((within(dialog).getByLabelText('Название проекта') as HTMLInputElement).value).toBe('Проблемный');
  });
});
