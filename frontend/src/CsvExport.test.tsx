import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import CsvExport from './CsvExport';

afterEach(() => {cleanup(); if (vi.isFakeTimers()) {vi.runOnlyPendingTimers(); vi.useRealTimers();} vi.unstubAllGlobals(); vi.restoreAllMocks();});

it('reports a rejected download and retries without navigating away', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({detail: 'Слишком много строк'}), {status: 413})));
  render(<CsvExport base="/workspaces/w1" entity="deals" pipelineId="p1"/>);
  fireEvent.click(screen.getByRole('button', {name: 'Скачать CSV'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Слишком много строк');
  expect(screen.getByRole('button', {name: 'Скачать CSV'})).toBeTruthy();
});

it('downloads a successful CSV through a temporary object URL with the selected pipeline', async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn(async (_url: string, _options?: RequestInit) => new Response('id;title\n1;Клиент', {headers: {'Content-Type': 'text/csv'}}));
  vi.stubGlobal('fetch', fetchMock);
  const create = vi.fn(() => 'blob:csv');
  vi.stubGlobal('URL', {createObjectURL: create, revokeObjectURL: vi.fn()});
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(<CsvExport base="/workspaces/w1" entity="deals" pipelineId="p1"/>);
  fireEvent.click(screen.getByRole('button', {name: 'Скачать CSV'}));
  await vi.waitFor(() => expect(create).toHaveBeenCalled());
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/workspaces/w1/exports/deals.csv?pipeline_id=p1');
});
