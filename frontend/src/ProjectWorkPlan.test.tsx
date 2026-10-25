import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import ProjectWorkPlan, {workTimeline, type WorkStage} from './ProjectWorkPlan';

let rows: WorkStage[];
let fail: boolean;
let fetchMock: ReturnType<typeof vi.fn>;
const stage = (overrides: Partial<WorkStage> = {}): WorkStage => ({id: 's1', project_id: 'p1', title: 'Дизайн', position: 0,
  status: 'PLANNED', manager_user_id: null, start_date: '2026-11-01', end_date: '2026-11-03', ...overrides});
beforeEach(() => {
  rows = [stage()]; fail = false;
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const method = options.method || 'GET';
    const data = options.body ? JSON.parse(String(options.body)) : null;
    const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status});
    if (method !== 'GET' && fail) return response({detail: 'Ошибка плана'}, 503);
    if (method === 'GET') return response(rows);
    if (method === 'POST') {const row = stage({id: 's2', title: data.title, position: rows.length, start_date: null, end_date: null}); rows.push(row); return response(row, 201);}
    if (method === 'PUT') {rows = data.ids.map((id: string, position: number) => ({...rows.find(row => row.id === id), position})); return response(rows);}
    if (method === 'PATCH') {rows = rows.map(row => url.endsWith('/' + row.id) ? {...row, ...data} : row); return response(rows.find(row => url.endsWith('/' + row.id)));}
    if (method === 'DELETE') {rows = rows.filter(row => !url.endsWith('/' + row.id)); return response(null, 204);}
    throw new Error(`${method} ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});
const renderPlan = (archived = false, view: 'plan' | 'gantt' = 'plan') => render(<ProjectWorkPlan base="/workspaces/w1" projectId="p1" members={[]}
  view={view} archived={archived} canDelete onChanged={async () => {}}/>);

it('preserves a failed plan draft, creates on retry and reorders stages', async () => {
  renderPlan();
  await screen.findByLabelText('Название этапа Дизайн');
  fireEvent.change(screen.getByLabelText('Новый этап работ'), {target: {value: 'Разработка'}});
  fail = true;
  fireEvent.click(screen.getByRole('button', {name: 'Добавить этап работ'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Ошибка плана');
  expect((screen.getByLabelText('Новый этап работ') as HTMLInputElement).value).toBe('Разработка');
  fail = false;
  fireEvent.click(screen.getByRole('button', {name: 'Добавить этап работ'}));
  await screen.findByLabelText('Название этапа Разработка');
  fireEvent.click(screen.getByRole('button', {name: 'Ниже Дизайн'}));
  await waitFor(() => expect(rows[0].title).toBe('Разработка'));
});

it('updates dates and completion status', async () => {
  renderPlan();
  await screen.findByLabelText('Окончание этапа Дизайн');
  fireEvent.change(screen.getByLabelText('Окончание этапа Дизайн'), {target: {value: '2026-11-10'}});
  fireEvent.change(screen.getByLabelText('Состояние этапа Дизайн'), {target: {value: 'DONE'}});
  fireEvent.click(screen.getByRole('button', {name: 'Сохранить этап Дизайн'}));
  await waitFor(() => expect(rows[0].end_date).toBe('2026-11-10'));
  expect(rows[0].status).toBe('DONE');
});

it('makes an archived plan read-only and renders a dated timeline', async () => {
  const view = renderPlan(true);
  const save = await screen.findByRole('button', {name: 'Сохранить этап Дизайн'});
  expect((save as HTMLButtonElement).disabled || !!save.closest('fieldset[disabled]')).toBe(true);
  expect((screen.getByRole('button', {name: 'Добавить этап работ'}) as HTMLButtonElement).closest('fieldset[disabled]')).toBeTruthy();
  view.unmount();
  renderPlan(true, 'gantt');
  expect(await screen.findByRole('img', {name: 'Дизайн: 2026-11-01 — 2026-11-03'})).toBeTruthy();
});

it('calculates inclusive UTC date-only spans across leap day without timezone shifts', () => {
  const result = workTimeline([stage({start_date: '2028-02-28', end_date: '2028-02-28'}), stage({id: 's2', start_date: '2028-02-29', end_date: '2028-03-01'}), stage({id: 's3', start_date: null, end_date: null})])!;
  expect(result.start).toBe('2028-02-28'); expect(result.end).toBe('2028-03-01');
  expect(result.bars).toHaveLength(2);
  expect(result.bars[0].width).toBeCloseTo(100 / 3);
  expect(result.bars[1].left).toBeCloseTo(100 / 3);
  expect(result.bars[1].width).toBeCloseTo(200 / 3);
});
