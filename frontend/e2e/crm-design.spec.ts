import {expect, test} from '@playwright/test';

// Design-only fixture: intercept every API request; never seed a real workspace.
test('ITG CRM filters, exact card opening and narrow-screen board stay usable', async ({page}) => {
  const stages = ['Новые обращения', 'В работе', 'Предложение', 'Успешно'].map((name, position) => ({
    id: `s${position}`, pipeline_id: 'p1', name, position, color: ['#e31e24', '#df9a73', '#858cb0', '#6b9e84'][position], stage_type: position === 3 ? 'WON' : 'OPEN',
  }));
  const titles = ['Корпоративный сайт', 'SEO-продвижение', 'Интернет-магазин', 'Редизайн сайта', 'Техническая поддержка', 'Лендинг для запуска', 'Разработка портала'];
  const deals = titles.map((title, i) => ({id: `d${i}`, workspace_id: 'w1', title, client_id: `c${i % 3}`, contact_id: null, pipeline_id: 'p1', stage_id: `s${[0, 0, 1, 1, 2, 2, 3][i]}`,
    responsible_user_id: 'u1', amount: String([180000, 65000, 420000, 210000, 45000, 95000, 680000][i]), currency: 'RUB', contact_name: ['Мария Волкова', 'Александр Иванов', 'Елена Смирнова'][i % 3], source: ['Сайт', 'Рекомендация', 'Входящий звонок'][i % 3], description: 'Обсудить задачи и согласовать следующий этап.',
    start_date: null, end_date: null, follow_up_at: i % 2 ? null : '2026-10-23T12:00:00Z', follow_up_action: 'call', follow_up_comment: null,
    created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-24T10:00:00Z'}));
  await page.route('**/api/v1/**', async route => {
    expect(route.request().method()).toBe('GET');
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {id: 'u1', first_name: 'Алексей', email: 'preview@example.invalid'};
    else if (path.endsWith('/workspaces')) body = [{id: 'w1', name: 'IT GROUP · Веб-студия', role: 'OWNER', currency: 'RUB', timezone: 'Europe/Moscow'}];
    else if (path.endsWith('/pipelines')) body = [{id: 'p1', name: 'Продажи студии', is_default: true, is_active: true, stages}];
    else if (path.endsWith('/members')) body = [{id: 'm1', user_id: 'u1', first_name: 'Алексей', email: 'preview@example.invalid', role: 'OWNER'}];
    else if (path.endsWith('/clients')) body = ['Альфа Групп', 'Студия «Форма»', 'ТехноЛайн'].map((name, i) => ({id: `c${i}`, name, type: 'COMPANY', phone: null, email: null, website: null, notes: null}));
    else if (path.endsWith('/deals')) body = deals;
    else if (path.endsWith('/custom-fields')) body = {values: []};
    await route.fulfill({json: body});
  });
  await page.setViewportSize({width: 1600, height: 1000});
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'CRM · Сделки'})).toBeVisible();
  await expect(page.getByRole('article')).toHaveCount(7);
  const noOverflow = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  expect(await noOverflow()).toBe(true);
  if (process.env.CRM_DESIGN_ARTIFACT_DIR) {
    await page.evaluate(() => {
      const note = document.createElement('div'); note.textContent = 'ДИЗАЙН-ПРЕВЬЮ · ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ';
      note.style.cssText = 'padding:9px 12px;background:#fff3da;color:#795922;font:10px Arial;letter-spacing:1px;text-align:center';
      document.querySelector('main')?.prepend(note);
    });
    await page.screenshot({path: `${process.env.CRM_DESIGN_ARTIFACT_DIR}/studioflow-crm-desktop.png`, fullPage: true});
  }
  await page.getByLabel('Поиск сделок').fill('Корпоративный');
  await expect(page.getByRole('article')).toHaveCount(1);
  await page.getByRole('article', {name: 'Открыть Корпоративный сайт', exact: true}).press('Enter');
  await expect(page.locator('.drawer').getByRole('heading', {name: 'Корпоративный сайт', exact: true})).toBeVisible();
  await page.locator('.drawer').getByRole('button', {name: 'Закрыть', exact: true}).click();
  await page.getByLabel('Поиск сделок').clear();
  await page.getByRole('button', {name: /^Нет дел/}).click();
  await expect(page.getByRole('article')).toHaveCount(3);
  await page.getByRole('button', {name: /^Все сделки/}).click();
  await page.setViewportSize({width: 390, height: 844});
  expect(await noOverflow()).toBe(true);
  expect(await page.locator('.kanban').evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
  if (process.env.CRM_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.CRM_DESIGN_ARTIFACT_DIR}/studioflow-crm-mobile.png`, fullPage: true});
  await page.locator('.kanban').evaluate(el => el.scrollLeft = el.scrollWidth);
  await expect(page.getByRole('article', {name: 'Открыть Разработка портала', exact: true})).toBeInViewport();
  await page.getByRole('button', {name: 'Открыть уведомления', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Уведомления', exact: true})).toBeVisible();
});
