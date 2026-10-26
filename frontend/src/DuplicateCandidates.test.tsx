import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import DuplicateCandidates from './DuplicateCandidates';

afterEach(() => {cleanup(); vi.unstubAllGlobals();});

it('reports a removed candidate instead of opening a blank editor', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({source: {id: 'c1', label: 'Компания'}, total: 1,
    items: [{id: 'c2', label: 'Удалённый кандидат', reasons: ['email']}]}))));
  render(<DuplicateCandidates base="/workspaces/w1" kind="client" objectId="c1" onClose={vi.fn()}
    onOpen={async () => {throw new Error('Кандидат больше недоступен');}}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Сравнить: Удалённый кандидат'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Кандидат больше недоступен');
});

it('explains possible matches and opens the exact candidate without merging', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({source: {id: 'c1', label: 'Основная компания'}, total: 1,
    items: [{id: 'c2', label: 'Вторая компания', reasons: ['phone', 'email']}]}))));
  const onOpen = vi.fn();
  render(<DuplicateCandidates base="/workspaces/w1" kind="client" objectId="c1" onOpen={onOpen} onClose={vi.fn()}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Сравнить: Вторая компания'}));
  expect(onOpen).toHaveBeenCalledWith('c2');
  expect(screen.getByText(/Совпадает: телефон, email/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Объединить'})).toBeNull();
});

it('clears failed results and retries the same source', async () => {
  let fail = true;
  vi.stubGlobal('fetch', vi.fn(async () => fail ? new Response(JSON.stringify({detail: 'Не удалось проверить'}), {status: 503}) :
    new Response(JSON.stringify({source: {id: 'c1', label: 'Компания'}, total: 0, items: []}))));
  render(<DuplicateCandidates base="/workspaces/w1" kind="client" objectId="c1" onOpen={vi.fn()} onClose={vi.fn()}/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Не удалось проверить');
  fail = false; fireEvent.click(screen.getByRole('button', {name: 'Повторить проверку дублей'}));
  expect(await screen.findByText('По этим правилам совпадений нет.')).toBeTruthy();
});

it('offers an explicit merge preview for both types only when allowed', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({source: {id: 'c1', label: 'Основная'}, total: 1,
    items: [{id: 'c2', label: 'Дубль', reasons: ['email']}]}))));
  const onMerge = vi.fn();
  const view = render(<DuplicateCandidates base="/workspaces/w1" kind="client" objectId="c1" onOpen={vi.fn()} onClose={vi.fn()} onMerge={onMerge}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Слияние: Дубль'}));
  expect(onMerge).toHaveBeenCalledWith('c2', 'c1');
  view.unmount();
  const contactView = render(<DuplicateCandidates base="/workspaces/w1" kind="contact" objectId="c1" onOpen={vi.fn()} onClose={vi.fn()} onMerge={onMerge}/>);
  fireEvent.click(await screen.findByRole('button', {name: 'Слияние: Дубль'}));
  expect(onMerge).toHaveBeenCalledTimes(2);
  contactView.unmount();
  render(<DuplicateCandidates base="/workspaces/w1" kind="contact" objectId="c1" onOpen={vi.fn()} onClose={vi.fn()}/>);
  await screen.findByRole('button', {name: 'Сравнить: Дубль'});
  expect(screen.queryByRole('button', {name: 'Слияние: Дубль'})).toBeNull();
});
