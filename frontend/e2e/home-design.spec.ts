import {expect, test} from '@playwright/test';

// Visual fixture only: no registration, seed, DB writes or production requests.
test('ITG home design keeps real navigation, responsive layout and explicit reporting semantics', async ({page}) => {
  const workspace = {id: 'design-workspace', name: 'IT GROUP · Веб-студия', role: 'OWNER', currency: 'RUB', timezone: 'Europe/Moscow'};
  const stages = [
    {stage_id: 's1', name: 'Новый запрос', count: 8, amount: '560000.00', stage_type: 'OPEN'},
    {stage_id: 's2', name: 'В работе', count: 6, amount: '420000.00', stage_type: 'OPEN'},
    {stage_id: 's3', name: 'Предложение', count: 4, amount: '360000.00', stage_type: 'OPEN'},
    {stage_id: 's4', name: 'Успешно', count: 7, amount: '845000.00', stage_type: 'WON'},
    {stage_id: 's5', name: 'Не реализовано', count: 3, amount: '175000.00', stage_type: 'LOST'},
  ].map(row => ({...row, pipeline_name: 'Продажи студии', currency: 'RUB'}));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown;
    if (path.endsWith('/auth/me')) body = {id: 'design-user', first_name: 'Алексей', email: 'preview@example.invalid'};
    else if (path.endsWith('/workspaces')) body = [workspace];
    else if (path.endsWith('/analytics')) body = {generated_at: '2026-10-24T11:30:00Z', timezone: 'Europe/Moscow', counts: {OPEN: 18, WON: 7, LOST: 3},
      conversion_percent: 70, stages, managers: [], work: {active_tasks: 24, overdue_tasks: 3, active_projects: 6, archived_projects: 12, overdue_followups: 2, missing_followups: 4}};
    else if (path.endsWith('/pipelines')) body = [{id: 'p1', name: 'Продажи студии', is_active: true, stages: []}];
    else body = [];
    await route.fulfill({json: body});
  });
  await page.setViewportSize({width: 1440, height: 1080});
  await page.goto('/#home');
  await expect(page.getByRole('heading', {name: 'Главная', exact: true})).toBeVisible();
  await expect(page.getByText('70%', {exact: true})).toBeVisible();
  await expect(page.getByRole('region', {name: 'Требует внимания', exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // Artifacts are clearly labelled: visual review must not imply these are live CRM figures.
  const markPreview = () => page.evaluate(() => {
    if (document.querySelector('[data-design-preview]')) return;
    const note = document.createElement('div'); note.dataset.designPreview = 'true';
    note.textContent = 'ДИЗАЙН-ПРЕВЬЮ · ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ';
    note.style.cssText = 'padding:9px 12px;background:#fff3da;color:#795922;font:10px Arial;letter-spacing:1px;text-align:center';
    document.querySelector('main')?.prepend(note);
  });
  if (process.env.HOME_DESIGN_ARTIFACT_DIR) {
    await markPreview();
    await page.screenshot({path: `${process.env.HOME_DESIGN_ARTIFACT_DIR}/studioflow-home-desktop.png`, fullPage: true});
  }
  await page.setViewportSize({width: 390, height: 844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('navigation', {name: 'Основная навигация'}).getByRole('button', {name: 'Задачи', exact: true})).toBeVisible();
  if (process.env.HOME_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.HOME_DESIGN_ARTIFACT_DIR}/studioflow-home-mobile.png`, fullPage: true});
  await page.getByRole('button', {name: 'Открыть уведомления', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Уведомления', exact: true})).toBeVisible();
  await expect(page.locator('.portalModule[data-module="Уведомления"]')).toBeVisible();
  await expect(page.locator('.homeShell')).toHaveCount(1);
});
