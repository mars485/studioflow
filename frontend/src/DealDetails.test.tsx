import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import DealDetails from './DealDetails';
import type {Deal, DealAttachment} from './api';

const deal: Deal = {id: 'd1', workspace_id: 'w1', title: 'Сайт', client_id: 'c1', contact_id: null, pipeline_id: 'p1', stage_id: 's1',
  responsible_user_id: null, amount: '100', currency: 'RUB', contact_name: null, source: null, description: null,
  start_date: null, end_date: null, utm_source: null, utm_medium: null, utm_campaign: null, utm_term: null, utm_content: null, http_referrer: null,
  follow_up_at: null, follow_up_action: null, follow_up_comment: null, created_at: '', updated_at: ''};
let attachments: DealAttachment[];
let fail: boolean;
let fetchMock: ReturnType<typeof vi.fn>;
const renderDetails = () => render(<DealDetails base="/workspaces/w1" deal={deal} members={[]} contacts={[]} onDealChange={vi.fn()}/>);

beforeEach(() => {
  attachments = [{id: 'old', filename: 'legacy.pdf', content_type: 'application/pdf', size_bytes: 2048,
    uploaded_by_user_id: null, uploaded_by_name: 'Legacy', created_at: '', has_content: false, sha256: null}];
  fail = false;
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), {status});
    if (options.method === 'POST' && url.includes('/attachments/upload?')) {
      if (fail) return response({detail: 'Файл слишком большой'}, 413);
      const file = options.body as File;
      const row: DealAttachment = {id: 'a1', filename: file.name, content_type: file.type, size_bytes: file.size,
        uploaded_by_user_id: 'u1', uploaded_by_name: 'Tester', created_at: '', has_content: true, sha256: 'a'.repeat(64)};
      attachments.unshift(row); return response(row, 201);
    }
    if (options.method === 'DELETE') {attachments = attachments.filter(row => !url.endsWith('/' + row.id)); return response(null, 204);}
    if (url.endsWith('/attachments')) return response(attachments);
    return response(url.endsWith('/custom-fields') ? {values: []} : []);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();});

it('uploads actual file bytes, exposes a download and keeps old metadata explicit', async () => {
  renderDetails();
  await screen.findByText('legacy.pdf');
  expect(screen.getByText('Только метаданные — файл не загружен')).toBeTruthy();
  expect(screen.queryByRole('link', {name: 'Скачать legacy.pdf'})).toBeNull();
  const file = new File(['binary content'], 'brief.txt', {type: 'text/plain'});
  fireEvent.change(screen.getByLabelText('Файл'), {target: {files: [file]}});
  fireEvent.click(screen.getByRole('button', {name: 'Загрузить файл'}));
  const link = await screen.findByRole('link', {name: 'Скачать brief.txt'});
  expect(link.getAttribute('href')).toBe('/api/v1/workspaces/w1/deals/d1/attachments/a1/download');
  const call = fetchMock.mock.calls.find(([url]) => url.includes('/attachments/upload?'))!;
  expect(call[1].body).toBe(file);
  expect(call[1].headers['X-StudioFlow-Request']).toBe('1');
  expect(call[1].headers['Content-Type']).toBe('text/plain');
  fireEvent.click(screen.getByRole('button', {name: 'Удалить вложение brief.txt'}));
  await waitFor(() => expect(screen.queryByRole('link', {name: 'Скачать brief.txt'})).toBeNull());
});

it('keeps the selected file and upload key on failure, allowing safe retry', async () => {
  renderDetails();
  await screen.findByText('legacy.pdf');
  const file = new File(['retry content'], 'retry.txt');
  fireEvent.change(screen.getByLabelText('Файл'), {target: {files: [file]}});
  fail = true;
  fireEvent.click(screen.getByRole('button', {name: 'Загрузить файл'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Файл слишком большой');
  fail = false;
  fireEvent.click(screen.getByRole('button', {name: 'Загрузить файл'}));
  await screen.findByRole('link', {name: 'Скачать retry.txt'});
  const calls = fetchMock.mock.calls.filter(([url]) => url.includes('/attachments/upload?'));
  expect(calls).toHaveLength(2);
  expect(calls[0][0]).toBe(calls[1][0]);
  expect(calls.every(([, options]) => options.body === file)).toBe(true);
});
