import {expect, test, type Page} from '@playwright/test';
import {expectReadableDarkUI} from './theme-audit';

const workspace = {id: 'w1', name: 'IT GROUP · Веб-студия', currency: 'RUB', timezone: 'Europe/Moscow', role: 'OWNER'};
const members = [{id: 'm1', user_id: 'u1', first_name: 'Алексей', email: 'preview@example.invalid', role: 'OWNER'},
  {id: 'm2', user_id: 'u2', first_name: 'Мария', email: 'team@example.invalid', role: 'MANAGER'}];
const clients = ['Альфа Групп', 'Студия «Форма»', 'ТехноЛайн'].map((name, i) => ({id: `c${i}`, name, type: 'COMPANY', phone: '+7 (000) 000-00-00', email: 'client@example.invalid', website: null, notes: null}));
const statuses = ['Запланировано', 'В работе', 'На проверке', 'Готово'].map((name, i) => ({id: `ts${i}`, name, position: i, is_final: i === 3}));
const tasks = ['Подготовить концепцию сайта', 'Согласовать прототип', 'Проверить адаптивную версию', 'Собрать требования', 'Обновить контент'].map((title, i) => ({
  id: `t${i}`, workspace_id: 'w1', title, status_id: `ts${i % 4}`, status_name: statuses[i % 4].name, is_final: i % 4 === 3,
  priority: ['HIGH', 'MEDIUM', 'LOW'][i % 3], assignee_user_id: i % 2 ? 'u2' : 'u1', deal_id: null, parent_task_id: null,
  due_at: '2026-10-26T12:00:00Z', start_at: '2026-10-24T09:00:00Z', checklist_total: 4, checklist_done: 2, estimate_minutes: 120,
}));
const projects = ['Корпоративный сайт', 'Интернет-магазин', 'SEO-продвижение'].map((title, i) => ({id: `pr${i}`, title, client_id: `c${i}`, status: 'ACTIVE', stage_id: 'ps1', stage_name: 'Разработка', manager_user_id: 'u1', start_date: '2026-10-20', end_date: '2026-11-20', tasks_total: 8, tasks_done: 3, amount: '180000', currency: 'RUB'}));

async function previewNote(page: Page) {
  await page.evaluate(() => {
    if (document.querySelector('[data-design-preview]')) return;
    const note = document.createElement('div'); note.dataset.designPreview = 'true';
    note.textContent = 'ДИЗАЙН-ПРЕВЬЮ · ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ';
    note.style.cssText = 'padding:9px 12px;background:#fff3da;color:#795922;font:10px Arial;letter-spacing:1px;text-align:center';
    document.querySelector('main')?.prepend(note);
  });
}

test('every module shares ITG shell and stays within desktop and mobile viewport', async ({page}) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/**', async route => {
    expect(route.request().method()).toBe('GET'); // Never writes to a database or exposes real tokens.
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {id: 'u1', first_name: 'Алексей', email: 'preview@example.invalid'};
    else if (path.endsWith('/workspaces')) body = [workspace];
    else if (path.endsWith('/members')) body = members;
    else if (path.endsWith('/clients')) body = clients;
    else if (path.endsWith('/contacts')) body = [{id: 'ct1', first_name: 'Мария', last_name: 'Волкова', email: 'contact@example.invalid', phone: '+7 (000) 000-00-00', client_ids: ['c0']}];
    else if (path.endsWith('/task-statuses')) body = statuses;
    else if (path.endsWith('/tasks')) body = tasks;
    else if (path.endsWith('/projects')) body = projects;
    else if (path.endsWith('/project-stages')) body = [{id: 'ps1', name: 'Разработка', position: 0}];
    else if (path.endsWith('/pipelines')) body = [{id: 'p1', name: 'Продажи студии', is_active: true, stages: []}];
    else if (path.endsWith('/organizations')) body = [{id: 'o1', name: 'IT GROUP', tax_id: '', tax_branch: '', bank: '', address: '', bank_account: '', bank_code: ''}];
    else if (path.endsWith('/invoices')) body = [{id: 'i1', number: '2026-042', issued_on: '2026-10-24', amount: '180000', currency: 'RUB', status: 'ISSUED', buyer: {name: 'Альфа Групп'}, project_id: 'pr0', deal_id: null}];
    else if (path.endsWith('/notifications/unread-count')) body = {count: 1};
    else if (path.endsWith('/notifications')) body = [{id: 'n1', workspace_id: 'w1', deal_id: 'd1', deal_title: 'Корпоративный сайт', author_name: 'Мария', body: 'Алексей, прототип готов к обсуждению. Посмотри комментарии перед встречей.', read_at: null, created_at: '2026-10-24T10:30:00Z'}];
    else if (path.endsWith('/webhooks/destinations')) body = {destinations: []};
    else if (path.endsWith('/search')) body = {items: [{kind: 'client', id: 'c0', label: 'Альфа Групп', state: 'COMPANY'}], total: 1};
    else if (path.endsWith('/analytics')) body = {generated_at: '2026-10-24T12:00:00Z', timezone: 'Europe/Moscow', counts: {OPEN: 18, WON: 7, LOST: 3}, conversion_percent: 70,
      stages: ['Новые обращения', 'В работе', 'Предложение', 'Успешно'].map((name, i) => ({stage_id: `s${i}`, name, pipeline_name: 'Продажи студии', currency: 'RUB', count: [8, 6, 4, 7][i], amount: ['560000', '420000', '360000', '845000'][i], stage_type: i === 3 ? 'WON' : 'OPEN'})),
      managers: [{user_id: 'u1', name: 'Алексей', currency: 'RUB', stage_type: 'OPEN', count: 10, amount: '720000'}],
      work: {active_tasks: 24, overdue_tasks: 3, active_projects: 6, archived_projects: 12, overdue_followups: 2, missing_followups: 4}};
    await route.fulfill({json: body});
  });
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto('/');
  const pages = [
    ['Задачи', 'Задачи', 'tasks'], ['Проекты', 'Проекты', 'projects'], ['Клиенты', 'Клиенты', 'clients'],
    ['Финансы', 'Финансы', 'finance'], ['Уведомления', 'Уведомления', 'notifications'], ['Интеграции', 'Интеграции', 'integrations'],
    ['Аналитика', 'Аналитика', 'analytics'], ['Настройки', 'Настройки студии', 'settings'], ['Поиск', 'Общий поиск', 'search'],
  ];
  for (const [nav, title, filename] of pages) {
    await page.setViewportSize({width: 1440, height: 1000});
    await page.getByRole('navigation', {name: 'Основная навигация'}).getByRole('button', {name: nav, exact: true}).click();
    await expect(page.getByRole('heading', {name: title, exact: true})).toBeVisible();
    await expect(page.getByText(/Загрузка|Расчёт показателей/, {exact: false})).toHaveCount(0);
    await expect(page.locator('.homeTopbar')).toHaveCount(1);
    await expect(page.locator('.sidebar .brand b')).toHaveText('IT GROUP');
    if (nav === 'Поиск') {
      await page.getByLabel('Поисковый запрос').fill('Альфа');
      await page.getByRole('button', {name: 'Найти в студии'}).click();
      await expect(page.getByRole('button', {name: 'Открыть компанию Альфа Групп'})).toBeVisible();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${nav}: desktop overflow`).toBe(true);
    await expectReadableDarkUI(page);
    if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) {
      await previewNote(page);
      await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/studioflow-${filename}-desktop.png`, fullPage: true});
    }
    await page.setViewportSize({width: 390, height: 844});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${nav}: mobile overflow`).toBe(true);
    await expect(page.getByRole('button', {name: 'Открыть уведомления', exact: true})).toBeVisible();
    if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/studioflow-${filename}-mobile.png`, fullPage: true});
    if (nav === 'Задачи') {
      await page.getByRole('button', {name: 'Календарь', exact: true}).click();
      await expect(page.locator('.taskCalendar')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'calendar mobile overflow').toBe(true);
      await page.getByRole('button', {name: 'Новая задача', exact: true}).click();
      const dialog = page.getByRole('dialog', {name: 'Новая задача', exact: true});
      await expect(dialog).toBeVisible();
      await expectReadableDarkUI(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'task form mobile overflow').toBe(true);
      if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/studioflow-task-form-mobile.png`});
      await dialog.getByRole('button', {name: 'Закрыть', exact: true}).click();
      await page.setViewportSize({width: 1440, height: 1000});
      if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/studioflow-calendar-desktop.png`, fullPage: true});
      await page.getByRole('button', {name: 'Список', exact: true}).click();
      await expect(page.getByRole('table')).toBeVisible();
      await page.setViewportSize({width: 390, height: 844});
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'task list mobile overflow').toBe(true);
    }
  }
  expect(errors).toEqual([]);
});

test('ITG account design preserves login and registration forms on narrow screens', async ({page}) => {
  await page.route('**/api/v1/**', route => route.fulfill({status: 401, json: {detail: 'Войдите в аккаунт'}}));
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Войти в StudioFlow'})).toBeVisible();
  if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/studioflow-login-desktop.png`, fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', {name: 'Создать аккаунт', exact: true}).click();
  await expect(page.getByLabel('Ваше имя')).toBeVisible();
  await expect(page.getByLabel('Пароль')).toHaveAttribute('minlength', '12');
  if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/studioflow-register-mobile.png`, fullPage: true});
  await page.getByRole('button', {name: 'У меня уже есть аккаунт'}).click();
  await expect(page.getByRole('heading', {name: 'Войти в StudioFlow'})).toBeVisible();
});

test('shared navigation preserves manager restrictions and module retry states', async ({page}) => {
  const paths: string[] = [];
  let failProjects = true;
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname; paths.push(path);
    if (path.endsWith('/projects') && failProjects) return route.fulfill({status: 503, json: {detail: 'Временно недоступно'}});
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {id: 'u2', first_name: 'Мария', email: 'team@example.invalid'};
    else if (path.endsWith('/workspaces')) body = [{...workspace, role: 'MANAGER'}];
    await route.fulfill({json: body});
  });
  await page.goto('/');
  const nav = page.getByRole('navigation', {name: 'Основная навигация'});
  await nav.getByRole('button', {name: 'Финансы', exact: true}).click();
  await expect(page.getByRole('alert')).toHaveText('Финансы доступны только владельцу и администратору.');
  await expect(page.getByRole('button', {name: 'Новый счёт'})).toHaveCount(0);
  await nav.getByRole('button', {name: 'Интеграции', exact: true}).click();
  await expect(page.getByRole('alert')).toHaveText('Интеграции доступны только владельцу и администратору.');
  expect(paths.some(path => /integration-tokens|invoices|organizations|webhooks/.test(path))).toBe(false);
  await nav.getByRole('button', {name: 'Проекты', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('Временно недоступно');
  failProjects = false;
  await page.getByRole('button', {name: 'Повторить', exact: true}).click();
  await expect(page.getByText('Проектов нет. Создайте проект из выигранной сделки или вручную.')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
