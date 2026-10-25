import {expect, test, type Page} from '@playwright/test';
import {expectReadableDarkUI} from './theme-audit';

const deal = {id: 'd1', workspace_id: 'w1', title: 'Дизайн портала', client_id: 'c1', contact_id: null,
  pipeline_id: 'p1', stage_id: 's1', amount: '180000.00', currency: 'RUB', source: 'Сайт',
  responsible_user_id: 'u1', contact_name: 'Мария', description: 'Согласовать прототип',
  start_date: null, end_date: null, follow_up_at: '2026-01-01T12:00:00Z', follow_up_action: 'call', follow_up_comment: null,
  created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00Z'};
const task = {id: 't1', workspace_id: 'w1', title: 'Проверить прототип', status_id: 'ts1', status_name: 'В работе',
  is_final: false, status: 'OPEN', priority: 'HIGH', assignee_user_id: 'u1', deal_id: 'd1', parent_task_id: null,
  description: 'Проверить адаптивную версию', start_at: null, due_at: '2026-01-01T12:00:00Z',
  checklist_total: 1, checklist_done: 0, estimate_minutes: 60};

// Theme acceptance uses intercepted requests only, never a live workspace.
async function mockWorkspace(page: Page) {
  await page.route('**/api/v1/**', async route => {
    expect(route.request().method()).toBe('GET');
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {id: 'u1', first_name: 'Алексей', email: 'theme@example.invalid'};
    else if (path.endsWith('/workspaces')) body = [{id: 'w1', name: 'ITG', currency: 'RUB', timezone: 'Europe/Moscow', role: 'OWNER'}];
    else if (path.endsWith('/pipelines')) body = [{id: 'p1', name: 'Продажи', is_active: true, is_default: true,
      stages: [{id: 's1', pipeline_id: 'p1', name: 'В работе', position: 0, stage_type: 'OPEN', color: '#89a7d0'}]}];
    else if (path.endsWith('/task-statuses')) body = [{id: 'ts1', name: 'В работе', position: 0, is_final: false}];
    else if (path.endsWith('/members')) body = [{id: 'm1', user_id: 'u1', first_name: 'Алексей', email: 'long-team-address@example.invalid', role: 'OWNER'}];
    else if (path.endsWith('/clients')) body = [{id: 'c1', name: 'Компания', type: 'COMPANY', phone: null, email: null, website: null, notes: null}];
    else if (path.endsWith('/deals')) body = [deal];
    else if (path.endsWith('/tasks')) body = new URL(route.request().url()).searchParams.has('parent_task_id') ? [] : [task];
    else if (path.endsWith('/my-day')) body = {tasks: [{task, deal_title: deal.title}], follow_ups: []};
    else if (path.endsWith('/custom-fields')) body = {values: []};
    else if (path.endsWith('/recurrence') || path.endsWith('/time-timer')) body = null;
    else if (path.endsWith('/time-entries')) body = {items: [], total_seconds: 0, timezone: 'Europe/Moscow', today: '2026-10-24'};
    else if (path.endsWith('/notifications/unread-count')) body = {count: 1};
    else if (path.endsWith('/webhooks/destinations')) body = {destinations: []};
    else if (path.endsWith('/analytics')) body = {
      generated_at: '2026-10-24T12:00:00Z', timezone: 'Europe/Moscow', counts: {OPEN: 12, WON: 4, LOST: 1},
      conversion_percent: 80, stages: [], managers: [],
      work: {active_tasks: 24, overdue_tasks: 3, active_projects: 6, archived_projects: 2, overdue_followups: 2, missing_followups: 1},
    };
    await route.fulfill({json: body});
  });
}

test('graphite tokens, local Cyrillic font and actual work summary survive responsive navigation', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/#home');
  const nav = page.getByRole('navigation', {name: 'Основная навигация'});
  await expect(nav.getByRole('button', {name: 'Главная', exact: true})).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('.shell')).toHaveCSS('background-color', 'rgb(24, 28, 27)');
  await expect(page.locator('.homeMetric').first()).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  const summary = page.locator('.homeOperationalSummary');
  await expect(summary).toContainText('24');
  await expect(summary).toContainText('6');
  await expect(summary).toContainText('2');
  expect(await page.evaluate(async () => {
    await document.fonts.load('14px "Golos Text"', 'Рабочая студия');
    return document.fonts.check('14px "Golos Text"', 'Рабочая студия');
  })).toBe(true);
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({width, height: 900});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow at ${width}`).toBe(true);
    await expect(nav.getByRole('button', {name: 'Задачи', exact: true})).toBeInViewport();
    await expect(page.getByRole('button', {name: 'Выйти', exact: true})).toBeVisible();
  }
  await nav.getByRole('button', {name: 'CRM', exact: true}).click();
  await expect(nav.getByRole('button', {name: 'CRM', exact: true})).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('heading', {name: 'CRM · Сделки'})).toBeVisible();
  await page.getByRole('button', {name: 'Новая сделка', exact: true}).click();
  await expect(page.locator('.dealModal')).toHaveCSS('background-color', 'rgb(32, 38, 36)');
  await expect(page.locator('.dealModal input').first()).toHaveCSS('color', 'rgb(238, 243, 239)');
});

test('calendar constrains long assignee labels and wide tables inside the viewport', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', {name: 'Задачи', exact: true}).click();
  await page.getByRole('button', {name: 'Календарь', exact: true}).click();
  await expect(page.locator('.taskCalendar')).toBeVisible();
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({width, height: 900});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `calendar overflow at ${width}`).toBe(true);
  }
});

test('keyboard focus is visible and reduced motion disables dialog motion', async ({page}) => {
  await mockWorkspace(page);
  await page.emulateMedia({reducedMotion: 'reduce'});
  await page.goto('/');
  const crm = page.getByRole('navigation').getByRole('button', {name: 'CRM', exact: true});
  await crm.focus();
  await expect(crm).toBeFocused();
  await expect(crm).toHaveCSS('outline-color', 'rgb(121, 217, 154)');
  await expect(crm).toHaveCSS('outline-style', 'solid');
  await expect(crm).toHaveCSS('transition-duration', '0s');
  await page.getByRole('button', {name: 'Новая сделка', exact: true}).click();
  await expect(page.locator('.dealModal')).toHaveCSS('animation-name', 'none');
});

test('account controls stay dark and readable at 375px without external font traffic', async ({page}) => {
  const external: string[] = [];
  page.on('request', request => {
    if (new URL(request.url()).origin !== new URL(page.url()).origin) external.push(request.url());
  });
  await page.route('**/api/v1/**', route => route.fulfill({status: 401, json: {detail: 'Войдите в аккаунт'}}));
  await page.setViewportSize({width: 375, height: 812});
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Войти в StudioFlow'})).toBeVisible();
  await expect(page.getByLabel('Email')).toHaveCSS('background-color', 'rgb(24, 28, 27)');
  await expect(page.getByRole('button', {name: 'Войти', exact: true})).toHaveCSS('background-color', 'rgb(121, 217, 154)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(external.filter(url => /fonts\.(googleapis|gstatic)\.com/.test(url))).toEqual([]);
});

test('primary, selected and text-only controls retain their semantic styling on hover', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/#home');
  const primary = page.getByRole('button', {name: 'Открыть CRM', exact: true});
  await primary.hover();
  await expect(primary).toHaveCSS('background-color', 'rgb(147, 228, 175)');
  await expect(primary).toHaveCSS('color', 'rgb(20, 37, 26)');
  await expect(page.getByRole('button', {name: 'Выйти', exact: true})).toHaveCSS('border-top-width', '0px');
  await expect(page.locator('.homeQuickStart button')).toHaveCSS('border-top-width', '0px');
  await expect(page.locator('.homeTextButton').first()).toHaveCSS('font-size', '12px');
  await primary.click();
  const selected = page.getByRole('button', {name: /^Все сделки/});
  await selected.hover();
  await expect(selected).toHaveCSS('background-color', 'rgb(36, 60, 45)');
  await expect(selected).toHaveCSS('color', 'rgb(147, 228, 175)');
  await page.getByRole('button', {name: 'Новая сделка', exact: true}).hover();
  await expect(page.getByRole('button', {name: 'Новая сделка', exact: true})).toHaveCSS('color', 'rgb(20, 37, 26)');
});

test('composite fields use a single focus ring instead of an inner frame and clipped outline', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/');
  const search = page.getByLabel('Поиск сделок');
  await search.focus();
  await expect(search).toHaveCSS('border-top-width', '0px');
  await expect(search).toHaveCSS('outline-style', 'none');
  await expect(page.locator('.search')).toHaveCSS('outline-style', 'solid');
  const pipeline = page.getByLabel('Воронка', {exact: true});
  await pipeline.focus();
  await expect(pipeline).toHaveCSS('outline-style', 'none');
  await expect(page.locator('.crmPipelineSelect')).toHaveCSS('outline-style', 'solid');
});

test('My Day and deal task editors no longer inherit light badges, purple actions or oversized checkboxes', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/');
  await page.locator('.crmSectionNav').getByRole('button', {name: 'Мой день', exact: true}).click();
  await expect(page.locator('.myDayOverdue').first()).toHaveCSS('background-color', 'rgb(58, 48, 34)');
  await page.locator('.myDayList').getByRole('button', {name: task.title, exact: true}).click();
  const drawer = page.getByRole('dialog', {name: 'Карточка сделки', exact: true});
  await expect(drawer).toBeVisible();
  const checkbox = drawer.locator('.dealTaskList input[type=checkbox]').first();
  await expect(checkbox).toHaveCSS('width', '16px');
  await expect(checkbox).toHaveCSS('height', '16px');
  await drawer.getByLabel('Название задачи', {exact: true}).fill('Новая задача');
  const add = drawer.getByRole('button', {name: 'Добавить задачу', exact: true});
  await add.hover();
  await expect(add).toHaveCSS('background-color', 'rgb(147, 228, 175)');
  await expect(add).toHaveCSS('color', 'rgb(20, 37, 26)');
  await expect(drawer.locator('input[type=file]')).toHaveCSS('background-color', 'rgb(24, 28, 27)');
  await expectReadableDarkUI(page);
  if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/itg-deal-editor.png`});
});

test('task drawer fields fill their labels and remain usable at phone and landscape sizes', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/');
  await page.getByRole('navigation', {name: 'Основная навигация'}).getByRole('button', {name: 'Задачи', exact: true}).click();
  await page.getByRole('article', {name: `Открыть ${task.title}`, exact: true}).click();
  const dialog = page.getByRole('dialog', {name: 'Карточка задачи', exact: true});
  await expect(dialog).toBeVisible();
  const description = dialog.locator('textarea').first();
  expect(await description.evaluate(el => Math.abs(el.getBoundingClientRect().width - el.parentElement!.getBoundingClientRect().width))).toBeLessThan(2);
  for (const viewport of [{width: 375, height: 812}, {width: 667, height: 375}]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await expect(dialog.getByRole('button', {name: 'Закрыть', exact: true})).toBeInViewport();
  }
  if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/itg-task-landscape.png`});
});

test('wide screens share one gutter and short windows scroll navigation without hiding logout', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/#home');
  for (const viewport of [{width: 1920, height: 1080}, {width: 1024, height: 600}, {width: 667, height: 375}]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByRole('button', {name: 'Выйти', exact: true})).toBeInViewport();
    const nav = page.getByRole('navigation', {name: 'Основная навигация'});
    await nav.getByRole('button', {name: 'Настройки', exact: true}).scrollIntoViewIfNeeded();
    await expect(nav.getByRole('button', {name: 'Настройки', exact: true})).toBeInViewport();
    const aligned = await page.evaluate(() => {
      const main = document.querySelector('main')!.getBoundingClientRect();
      const bar = document.querySelector('.homeTopbar')!.getBoundingClientRect();
      return Math.abs(main.left - bar.left) <= 1 && Math.abs(main.right - bar.right) <= 1;
    });
    expect(aligned).toBe(true);
  }
});

test('a long CSV error wraps below the toolbar controls instead of stretching the mobile page', async ({page}) => {
  await mockWorkspace(page);
  await page.route('**/exports/*.csv*', route => route.fulfill({status: 503, json: {detail: 'Экспорт временно недоступен. Повторите попытку после восстановления соединения с сервером.'}}));
  await page.setViewportSize({width: 375, height: 812});
  await page.goto('/');
  await page.getByRole('button', {name: 'Скачать CSV', exact: true}).click();
  await expect(page.locator('.csvExport [role=alert]')).toContainText('Экспорт временно недоступен');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expectReadableDarkUI(page);
});

test('workspace picker uses the graphite popup and keeps native keyboard selection', async ({page}) => {
  await mockWorkspace(page);
  await page.route('**/api/v1/workspaces', route => route.fulfill({json: [
    {id: 'w1', name: 'IT GROUP · Демо (учебные данные)', currency: 'RUB', timezone: 'Europe/Moscow', role: 'OWNER'},
    {id: 'w2', name: 'Вторая студия', currency: 'RUB', timezone: 'Europe/Moscow', role: 'OWNER'},
  ]}));
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto('/');
  const workspace = page.getByLabel('Рабочее пространство', {exact: true});
  await expect(workspace).toBeEnabled();
  expect(await page.evaluate(() => CSS.supports('appearance', 'base-select'))).toBe(true);
  await workspace.click();
  await expect(workspace).toHaveCSS('appearance', 'base-select');
  expect(await workspace.evaluate(el => el.matches(':open'))).toBe(true);
  expect(await workspace.evaluate(el => getComputedStyle(el, '::picker(select)').backgroundColor)).toBe('rgb(32, 38, 36)');
  await expect(workspace.locator('option:checked')).toHaveCSS('background-color', 'rgb(36, 60, 45)');
  if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/itg-workspace-picker.png`});
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(workspace).toHaveValue('w2');
  expect(await workspace.evaluate(el => el.matches(':open'))).toBe(false);
});

test('client actions align with the CSV button and its hint never changes toolbar geometry', async ({page}) => {
  await mockWorkspace(page);
  await page.goto('/');
  await page.getByRole('navigation', {name: 'Основная навигация'}).getByRole('button', {name: 'Клиенты', exact: true}).click();
  const create = page.getByRole('button', {name: 'Новая компания', exact: true});
  const csv = page.getByRole('button', {name: 'Скачать CSV', exact: true});
  const hint = page.locator('.csvExportHint');
  await expect(create).toBeEnabled();
  await expect(hint).toBeHidden();
  await expect(csv).toHaveAttribute('aria-describedby', await hint.getAttribute('id') || 'missing');
  const before = await create.boundingBox();
  const csvBox = await csv.boundingBox();
  expect(Math.abs(before!.y - csvBox!.y)).toBeLessThan(1);
  expect(Math.abs(before!.height - csvBox!.height)).toBeLessThan(1);
  await csv.hover();
  await expect(hint).toBeVisible();
  expect(await create.boundingBox()).toEqual(before);
  await csv.focus();
  await page.keyboard.press('Escape');
  await expect(hint).toBeHidden();
  if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/itg-client-actions.png`});
  for (const width of [375, 768]) {
    await page.setViewportSize({width, height: 900});
    await csv.focus();
    await page.keyboard.press('Tab');
    await csv.focus();
    await expect(hint).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('wide settings selects keep the picker arrow at the right edge rather than beside the text', async ({page}) => {
  await mockWorkspace(page);
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto('/');
  await page.getByRole('navigation', {name: 'Основная навигация'}).getByRole('button', {name: 'Настройки', exact: true}).click();
  const workspace = page.getByLabel('Студия в настройках', {exact: true});
  await expect(workspace).toBeEnabled();
  for (const select of [workspace, page.getByRole('combobox', {name: 'Роль', exact: true})]) {
    const arrowSpace = await select.evaluate(el => parseFloat(getComputedStyle(el, '::picker-icon').marginLeft));
    expect(arrowSpace).toBeGreaterThan(100);
    await select.click();
    expect(await select.evaluate(el => el.matches(':open'))).toBe(true);
    await page.keyboard.press('Escape');
  }
  if (process.env.PORTAL_DESIGN_ARTIFACT_DIR) await page.screenshot({path: `${process.env.PORTAL_DESIGN_ARTIFACT_DIR}/itg-settings-arrows.png`, fullPage: true});
  await page.setViewportSize({width: 375, height: 812});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('integration refresh clears the next card and notification checkbox aligns with its label', async ({page}) => {
  await mockWorkspace(page);
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto('/');
  const nav = page.getByRole('navigation', {name: 'Основная навигация'});
  await nav.getByRole('button', {name: 'Интеграции', exact: true}).click();
  const refresh = page.getByRole('button', {name: 'Обновить интеграции', exact: true});
  await expect(refresh).toBeEnabled();
  const nextCard = page.locator('.settingsCard').filter({has: page.getByRole('heading', {name: 'Токены · только leads:create', exact: true})});
  const buttonBox = await refresh.boundingBox(), cardBox = await nextCard.boundingBox();
  expect(cardBox!.y - buttonBox!.y - buttonBox!.height).toBeGreaterThanOrEqual(20);
  await nav.getByRole('button', {name: 'Уведомления', exact: true}).click();
  const checkbox = page.getByRole('checkbox', {name: 'Только непрочитанные', exact: true});
  await expect(checkbox).toBeEnabled();
  for (const width of [1440, 375]) {
    await page.setViewportSize({width, height: 900});
    const label = page.locator('.notificationTools .checkboxLabel');
    await expect(label).toHaveCSS('gap', '8px');
    const inputBox = await checkbox.boundingBox(), labelBox = await label.boundingBox();
    expect(Math.abs(inputBox!.y + inputBox!.height / 2 - labelBox!.y - labelBox!.height / 2)).toBeLessThan(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await checkbox.check();
  await expect(checkbox).toBeChecked();
});
