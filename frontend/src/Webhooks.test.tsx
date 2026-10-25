import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import Webhooks from './Webhooks';

let configured: boolean;
let fail: boolean;
let subs: {id: string; destination: string; events: string[]; enabled: boolean}[];
beforeEach(() => {
  configured = true; fail = false; subs = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    if (url.endsWith('/destinations')) return new Response(JSON.stringify({destinations: configured ? ['n8n'] : []}));
    if (url.includes('/deliveries/')) return new Response(JSON.stringify([]));
    if (options.method === 'POST') {
      if (fail) return new Response(JSON.stringify({detail: 'Ошибка подписки'}), {status: 503});
      const row = {id: 's1', ...JSON.parse(String(options.body)), enabled: true}; subs.push(row);
      return new Response(JSON.stringify({...row, signing_secret: 'one-time-signing-secret'}), {status: 201});
    }
    return new Response(JSON.stringify(subs));
  }));
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('requires operator configuration before allowing outgoing subscriptions', async () => {
  configured = false;
  render(<Webhooks base="/workspaces/w1"/>);
  expect(await screen.findByText('Исходящие отправки не настроены оператором.')).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Создать подписку webhook'})).toBeNull();
});

it('preserves a failed subscription draft and shows a signing key only once', async () => {
  const view = render(<Webhooks base="/workspaces/w1"/>);
  fireEvent.change(await screen.findByLabelText('Назначение webhook'), {target: {value: 'n8n'}});
  fail = true; fireEvent.click(screen.getByRole('button', {name: 'Создать подписку webhook'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Ошибка подписки');
  expect((screen.getByLabelText('Назначение webhook') as HTMLSelectElement).value).toBe('n8n');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Создать подписку webhook'}));
  expect((await screen.findByLabelText('Ключ подписи webhook') as HTMLTextAreaElement).value).toBe('one-time-signing-secret');
  fireEvent.click(screen.getByRole('button', {name: 'Скрыть ключ webhook'}));
  view.unmount(); render(<Webhooks base="/workspaces/w1"/>);
  await screen.findByRole('button', {name: 'Отключить webhook n8n'});
  expect(screen.queryByLabelText('Ключ подписи webhook')).toBeNull();
});
