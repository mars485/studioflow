import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import App from './App';
import Auth from './Auth';
import WorkspaceSettings from './WorkspaceSettings';

const response = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), {status});
const user = {id: 'u1', email: 'owner@example.com', first_name: 'Owner'};
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});

it('sends login credentials with CSRF header and preserves form on failure', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response({detail: 'Неверный email или пароль'}, 401))
    .mockResolvedValueOnce(response(user));
  vi.stubGlobal('fetch', fetchMock);
  const loggedIn = vi.fn();
  render(<Auth onLogin={loggedIn}/>);
  fireEvent.change(screen.getByLabelText('Email'), {target: {value: user.email}});
  fireEvent.change(screen.getByLabelText('Пароль'), {target: {value: 'long-password-123'}});
  fireEvent.click(screen.getByRole('button', {name: /^Войти$/}));
  expect((await screen.findByRole('alert')).textContent).toContain('Неверный');
  expect((screen.getByLabelText('Email') as HTMLInputElement).value).toBe(user.email);
  fireEvent.click(screen.getByRole('button', {name: /^Войти$/}));
  await waitFor(() => expect(loggedIn).toHaveBeenCalledWith(user));
  expect(fetchMock.mock.calls[0][1]).toMatchObject({credentials: 'same-origin', headers: {'X-StudioFlow-Request': '1'}});
});

it('registers an account through the form', async () => {
  const fetchMock = vi.fn().mockResolvedValue(response(user, 201));
  vi.stubGlobal('fetch', fetchMock);
  const loggedIn = vi.fn();
  render(<Auth onLogin={loggedIn}/>);
  fireEvent.click(screen.getByRole('button', {name: 'Создать аккаунт'}));
  fireEvent.change(screen.getByLabelText('Ваше имя'), {target: {value: user.first_name}});
  fireEvent.change(screen.getByLabelText('Email'), {target: {value: user.email}});
  fireEvent.change(screen.getByLabelText('Пароль'), {target: {value: 'long-password-123'}});
  fireEvent.click(screen.getByRole('button', {name: 'Зарегистрироваться'}));
  await waitFor(() => expect(loggedIn).toHaveBeenCalledWith(user));
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/auth/register');
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({first_name: user.first_name});
});

it('restores the account then removes private UI after logout', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/auth/me')) return response(user);
    if (url.endsWith('/auth/logout')) return response(null, 204);
    if (url.endsWith('/workspaces')) return response([]);
    throw new Error(url);
  }));
  render(<App/>);
  expect(await screen.findByText(user.first_name)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Выйти'}));
  expect(await screen.findByRole('heading', {name: 'Войти в StudioFlow'})).toBeTruthy();
  expect(screen.queryByText(user.email)).toBeNull();
});

it('offers a retry on unavailable session service instead of pretending logout', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response({}, 503)).mockResolvedValueOnce(response({}, 401));
  vi.stubGlobal('fetch', fetchMock);
  render(<App/>);
  expect(await screen.findByRole('alert')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Повторить'}));
  expect(await screen.findByRole('heading', {name: 'Войти в StudioFlow'})).toBeTruthy();
});

it('clears private UI when a protected API request rejects an expired session', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/auth/me')
    ? response(user) : response({detail: 'Сессия истекла'}, 401)));
  render(<App/>);
  expect(await screen.findByRole('heading', {name: 'Войти в StudioFlow'})).toBeTruthy();
  expect(screen.queryByText(user.email)).toBeNull();
});

it('creates a workspace and displays server errors for membership changes', async () => {
  let spaces: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
    if (url.endsWith('/workspaces') && options.method === 'POST') {
      const workspace = {id: 'w1', name: 'New studio', role: 'OWNER'};
      spaces = [workspace]; return response(workspace, 201);
    }
    if (url.endsWith('/workspaces')) return response(spaces);
    if (options.method === 'POST') return response({detail: 'Пользователь должен сначала зарегистрироваться'}, 404);
    if (url.endsWith('/members')) return response([{...user, id: 'm1', user_id: user.id, role: 'OWNER'}]);
    throw new Error(url);
  }));
  render(<WorkspaceSettings/>);
  await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
  fireEvent.change(screen.getByLabelText('Название новой студии'), {target: {value: 'New studio'}});
  fireEvent.click(screen.getByRole('button', {name: 'Создать студию'}));
  expect(await screen.findByText('Ваша роль: Владелец')).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
  fireEvent.change(screen.getByLabelText('Email участника'), {target: {value: 'new@example.com'}});
  fireEvent.click(screen.getByRole('button', {name: 'Добавить участника'}));
  expect((await screen.findByRole('alert')).textContent).toContain('зарегистрироваться');
  expect((screen.getByLabelText('Email участника') as HTMLInputElement).value).toBe('new@example.com');
});

it('hides workspace management controls from managers', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/workspaces')
    ? response([{id: 'w1', name: 'Studio', role: 'MANAGER'}])
    : response([{...user, id: 'm1', role: 'OWNER'}])));
  render(<WorkspaceSettings/>);
  expect(await screen.findByText(user.email)).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Добавить участника'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Удалить участника'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Сохранить название'})).toBeNull();
});
