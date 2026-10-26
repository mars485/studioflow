import {afterEach, expect, it} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import WebsiteLeadContext, {type WebsiteContext} from './WebsiteLeadContext';

const context: WebsiteContext = {form_kind: 'audit', source_url: 'https://itgsystem.ru/audit', submitted_at: '2026-10-26T09:00:00Z',
  contact_text: '@person', website: 'https://customer.example/', privacy_consent: true, audit_email_consent: true,
  policy_version: 'privacy-2026-10', client_type: 'PERSON', utm_source: 'search', utm_campaign: null, utm_medium: null,
  utm_term: null, utm_content: null};
afterEach(cleanup);

it('discloses preserved website context with explicit source-attested consent', () => {
  render(<WebsiteLeadContext context={context}/>);
  const summary = screen.getByText('Контекст заявки сайта · Аудит');
  const details = summary.closest('details')!;
  expect(details.open).toBe(false);
  fireEvent.click(summary);
  expect(details.open).toBe(true);
  expect(screen.getByText('@person')).toBeTruthy();
  expect(screen.getByText('Частное лицо')).toBeTruthy();
  expect(screen.getByText('Согласие заявлено источником; не рекламная подписка')).toBeTruthy();
  expect(screen.getByText('privacy-2026-10')).toBeTruthy();
  expect(screen.getByText('search')).toBeTruthy();
});

it('renders untrusted source text without HTML execution, links or external loads', () => {
  const hostile = '<img src="https://evil.invalid/pixel" onerror="alert(1)">';
  const view = render(<WebsiteLeadContext context={{...context, form_kind: 'contact', contact_text: hostile, policy_version: null,
    audit_email_consent: false, website: null}}/>);
  fireEvent.click(screen.getByText('Контекст заявки сайта · Обращение'));
  expect(screen.getByText(hostile)).toBeTruthy();
  expect(view.container.querySelector('img, script, iframe, a')).toBeNull();
  expect(screen.getByText('Источник не передал версию')).toBeTruthy();
  expect(screen.getByText('Согласие не заявлено')).toBeTruthy();
});
