import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import LiveDashboard, {type Analytics} from './LiveDashboard';

let report: Analytics;
let fail: boolean;
let calls: string[];
beforeEach(() => {
  calls = []; fail = false;
  report = {generated_at: '2026-10-24T12:00:00Z', timezone: 'Asia/Yekaterinburg', counts: {OPEN: 1, WON: 2, LOST: 2}, conversion_percent: 50,
    stages: [{stage_id: 's1', name: 'Новые', stage_type: 'OPEN', pipeline_name: 'Продажи', currency: 'RUB', count: 1, amount: '100'}], managers: [],
    work: {active_tasks: 3, overdue_tasks: 1, active_projects: 2, archived_projects: 0, overdue_followups: 1, missing_followups: 1}};
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    if (url === '/api/v1/workspaces') return new Response(JSON.stringify([{id: 'w1', name: 'Студия', role: 'MANAGER'}]));
    if (url.includes('/pipelines?')) return new Response(JSON.stringify([{id: 'p1', name: 'Продажи', is_active: true}]));
    if (fail) return new Response(JSON.stringify({detail: 'Нет связи с БД'}), {status: 503});
    return new Response(JSON.stringify(report));
  }));
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('renders server KPI, applies cohort filters and updates after a reload', async () => {
  const props = {detailed: true, openCRM: vi.fn()};
  const view = render(<LiveDashboard {...props}/>);
  await screen.findByText('50%');
  expect(within(screen.getByRole('region', {name: 'Сводка работы студии'})).getByText('3')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Созданы с'), {target: {value: '2026-10-01'}});
  await vi.waitFor(() => expect(calls.some(url => url.includes('from_date=2026-10-01'))).toBe(true));
  report = {...report, conversion_percent: 100};
  view.unmount(); render(<LiveDashboard {...props}/>);
  expect(await screen.findByText('100%')).toBeTruthy();
  expect(screen.queryByText('АН «Квадрат»')).toBeNull();
});

it('shows a failed calculation without invented metrics and allows retry', async () => {
  fail = true; render(<LiveDashboard detailed={false} openCRM={vi.fn()}/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Нет связи с БД');
  expect(screen.queryByRole('region', {name: 'Показатели продаж'})).toBeNull();
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Повторить расчёт'}));
  expect(await screen.findByText('50%')).toBeTruthy();
});

it('home uses server figures and provides working task, search and CRM actions', async () => {
  const onNavigate = vi.fn(); const openCRM = vi.fn();
  render(<LiveDashboard detailed={false} userName="Менеджер" onNavigate={onNavigate} openCRM={openCRM}/>);
  await screen.findByText('50%');
  fireEvent.click(screen.getByRole('button', {name: /^Открыть CRM$/}));
  expect(openCRM).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole('button', {name: 'Открыть задачи студии'}));
  expect(onNavigate).toHaveBeenCalledWith('Задачи');
  fireEvent.click(screen.getByRole('button', {name: /Поиск по рабочему пространству/}));
  expect(onNavigate).toHaveBeenCalledWith('Поиск');
  expect(screen.getByText(/Конверсия не учитывает открытые сделки/)).toBeTruthy();
});
