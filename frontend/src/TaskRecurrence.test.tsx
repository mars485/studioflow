import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import TaskRecurrence, {type Recurrence} from './TaskRecurrence';

let rule: Recurrence | null;
let fail: boolean;
beforeEach(() => {
  rule = null; fail = false;
  vi.stubGlobal('fetch', vi.fn(async (_url: string, options: RequestInit = {}) => {
    if (options.method === 'PUT') {
      if (fail) return new Response(JSON.stringify({detail: 'Ошибка повторения'}), {status: 503});
      rule = {...JSON.parse(String(options.body)), processed: false, next_task_id: null, stop_reason: null};
    }
    return new Response(JSON.stringify(rule), {status: 200});
  }));
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});
const props = {base: '/workspaces/w1', taskId: 't1', isFinal: false, isChild: false, onOpenTask: vi.fn()};

it('preserves failed recurrence settings and restores saved settings on remount', async () => {
  const view = render(<TaskRecurrence {...props}/>);
  await screen.findByLabelText('Повторять задачу');
  fireEvent.click(screen.getByLabelText('Повторять задачу'));
  fireEvent.change(screen.getByLabelText('Интервал, суток'), {target: {value: '14'}});
  fail = true; fireEvent.click(screen.getByRole('button', {name: 'Сохранить повторение'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Ошибка повторения');
  expect((screen.getByLabelText('Интервал, суток') as HTMLInputElement).value).toBe('14');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Сохранить повторение'}));
  await vi.waitFor(() => expect(rule?.interval_days).toBe(14));
  view.unmount(); render(<TaskRecurrence {...props}/>);
  expect((await screen.findByLabelText('Интервал, суток') as HTMLInputElement).value).toBe('14');
});

it('opens the generated successor without enabling reconfiguration of a processed task', async () => {
  rule = {interval_days: 7, remaining: 1, enabled: true, processed: true, next_task_id: 't2', stop_reason: null};
  const onOpenTask = vi.fn();
  render(<TaskRecurrence {...props} isFinal onOpenTask={onOpenTask}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Открыть следующую задачу'}));
  expect(onOpenTask).toHaveBeenCalledWith('t2');
  expect(screen.getByLabelText('Интервал, суток').closest('fieldset[disabled]')).toBeTruthy();
});
