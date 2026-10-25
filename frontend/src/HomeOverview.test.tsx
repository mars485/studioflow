import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen, within} from '@testing-library/react';
import HomeOverview from './HomeOverview';
import type {Analytics} from './LiveDashboard';

afterEach(cleanup);

it('uses the supplied workspace figures for the operational summary and updates them without invented trends', () => {
  const data: Analytics = {
    generated_at: '2026-10-24T12:00:00Z', timezone: 'Europe/Moscow',
    counts: {OPEN: 0, WON: 0, LOST: 0}, conversion_percent: null, stages: [], managers: [],
    work: {active_tasks: 24, overdue_tasks: 3, active_projects: 6, archived_projects: 2, overdue_followups: 2, missing_followups: 1},
  };
  const props = {openCRM: vi.fn(), onNavigate: vi.fn()};
  const view = render(<HomeOverview data={data} {...props}/>);
  const summary = screen.getAllByRole('definition')[0].closest('dl')!;
  // Accessible terms and their adjacent values preserve the meaning of the data.
  expect(within(summary).getByText('Задачи в работе').nextElementSibling?.textContent).toBe('24');
  expect(within(summary).getByText('Активные проекты').nextElementSibling?.textContent).toBe('6');
  expect(within(summary).getByText('Follow-up просрочены').nextElementSibling?.textContent).toBe('2');
  view.rerender(<HomeOverview data={{...data, work: {...data.work, active_tasks: 0, overdue_followups: 0}}} {...props}/>);
  expect(within(summary).getByText('Задачи в работе').nextElementSibling?.textContent).toBe('0');
  expect(within(summary).getByText('Follow-up просрочены').nextElementSibling?.className).toBe('');
  expect(screen.getByText('Конверсия закрытых')).toBeTruthy();
  expect(screen.queryByText('Рост выручки')).toBeNull();
});
