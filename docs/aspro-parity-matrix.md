# Матрица функционального соответствия Аспро.Cloud

Статус на 24.10.2026. Источник UI — разрешённый тестовый портал `https://7e96.aspro.cloud/`; `https://aspro.cloud/help/` — официальная документация. Наличие приложения в каталоге подтверждает только доступность установки, а не проверенный сценарий. Исходный код, оформление, тексты и данные Аспро.Cloud не переносятся. TESTED относится только к описанному объёму, не ко всему модулю референса.

Статусы: `NOT_RESEARCHED`, `SPECIFIED`, `NOT_IMPLEMENTED`, `IN_PROGRESS`, `IMPLEMENTED`, `TESTED`, `VERIFIED`, `BLOCKED`. `VERIFIED` требует работающего сценария StudioFlow и доказательства теста. Ни одна строка пока не имеет такого полного доказательства.

| Модуль | Функция | Источник/наблюдение | Приоритет | Backend | Frontend | Тесты | Статус |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Доступ | Регистрация, вход, выход, роли workspace | StudioFlow код | P0 | `backend/app/api/v1/auth.py`, `workspaces.py` | `frontend/src/Auth.tsx`, `WorkspaceSettings.tsx` | `backend/tests/test_auth.py`, `frontend/src/Auth.test.tsx` | TESTED |
| CRM | Сделка: CRUD и Kanban | UI: «Сделки»; StudioFlow код | P0 | `backend/app/api/v1/crm.py` | `frontend/src/CRM.tsx` | `backend/tests/test_crm.py`, `frontend/src/CRM.test.tsx`, `frontend/e2e/crm.spec.ts` | TESTED |
| CRM | Следующее действие на сделке | StudioFlow код | P0 | `crm.py` | `CRM.tsx` | `test_crm.py`, `CRM.test.tsx`, `crm.spec.ts` | TESTED |
| CRM | Завершение follow-up с отдельной историей | [Справка: связи со сделкой](https://aspro.cloud/help/articles/3301-3302-7340--svyazi-so-sdelkoj/), [«Мои дела»](https://aspro.cloud/help/articles/3301-6977-7377--vidzhet-moi-dela/); UI Аспро не проверен | P1 | `backend/app/models/entities.py`, миграция `0006`, `backend/app/api/v1/crm.py` | `frontend/src/CRM.tsx` | backend 27/27, frontend 17/17, E2E 1/1; [сценарий](aspro-follow-up-completion.md) | TESTED |
| CRM | Счётчики и фильтры дел: сегодня, просрочены, без дела | UI `7e96.aspro.cloud`, доска сделок; REA и AX-снимок 23.10.2026 | P1 | Поля follow-up в сделке | `frontend/src/CRM.tsx` | frontend 18/18, сборка и E2E 1/1 | TESTED |
| CRM | Поля создания сделки: название, сумма, источник, даты, ответственный, наблюдатели, клиент, описание, файлы, теги, пользовательские поля | REA и UI: форма новой сделки, `7e96.aspro.cloud` | P1 | Частично; ответственный с проверкой membership | Частично; выбор ответственного | Backend 28/28, frontend 17/17, E2E 1/1 | IN_PROGRESS |
| CRM | Сроки начала и окончания сделки | UI: карточка сделки; REA `ev_6b425240cf959e4eaa21dd519e3d6424dfe752bcc24748fbe01eeb8603a9df8f` | P1 | `deals.start_date`, `end_date`; миграция `0008`, проверка порядка | Форма и карточка | Backend 33/33, frontend 23/23, E2E 1/1; [сценарий](aspro-deal-dates.md) | TESTED |
| CRM | Задача, связанная со сделкой | UI: «Задача» в ленте сделки; REA `ev_e976ad65c331be69573d765853ce2503467f052b4921c4aae5cdac6e526cd1a8` | P1 | `deal_tasks`, миграция `0009`, scoped CRUD, автор завершения | Список и форма в карточке | Backend 35/35, frontend 24/24, E2E 1/1; [сценарий](aspro-deal-tasks.md) | TESTED |
| CRM | Напоминания о задачах сделки | [Справка Аспро.Cloud](https://aspro.cloud/help/articles/3281-7221--napominaniya-v-zadachah/); форма задачи в UI Аспро, REA `ev_e976ad65c331be69573d765853ce2503467f052b4921c4aae5cdac6e526cd1a8` | P1 | `task_reminders`, миграция `0010`, scoped CRUD, пересчёт времени срабатывания | Форма в задаче и сработавшие напоминания в «Мой день» | Backend 37/37, frontend 26/26, сборка, E2E 1/1; [сценарий](aspro-task-reminders.md) | TESTED |
| CRM | «Мой день»: назначенные задачи и следующие контакты | [Справка Аспро.Cloud](https://aspro.cloud/help/articles/3301-6977-7377--vidzhet-moi-dela/); обзор задач портала, REA `ev_9b7bdda217badd2afe05bd50e0159a39c1106ddbf2474855bb815d01dffe6efe` | P1 | Scoped `GET /my-day`, только активные сделки | Список с подсветкой сроков, переходом к сделке и завершением задачи | Backend 36/36, frontend-тесты и сборка, E2E 1/1; [сценарий](aspro-my-day.md) | IN_PROGRESS |
| CRM | Лента активностей и история стадий | `docs/REFERENCES.md`; заметки и переходы стадий реализованы | P1 | Модель, миграции `0004`–`0005`, scoped API, автоматический аудит стадии | Лента в карточке | Frontend 15/15; backend 26/26; E2E 1/1 | TESTED |
| CRM | Контакты и карточка компании | UI `7e96.aspro.cloud`, REA `ev_6669d37eea8568c3eec6c4ba07c12af266b7a42cae77828b18fe40d5fc5f5034`, `ev_326327d4880a21f89e88d5bcdd6a2ee6e00524245cb1801f1a732ebe14b21500` | P1 | Профили компаний и контактов, связи со сделками, workspace isolation, миграция `0007` | Каталоги компаний/контактов, выбор контакта в сделке | Backend 32/32, frontend 22/22, E2E 1/1; [компании](aspro-company-profile.md), [контакты](aspro-contacts.md) | IN_PROGRESS |
| CRM | Настраиваемые воронки и стадии | UI `7e96.aspro.cloud`, REA `ev_699c303293b333a90ee8fb190c2420ec4577870624be9f0f5c7f069bed40543c`; [справка Аспро](https://aspro.cloud/help/articles/3301-7329-7330--sozdanie-i-redaktirovanie-voronki-prodazh/) | P1 | Жизненный цикл воронок, CRUD стадий, порядок, защита сделок | UI выбора и управления воронками/стадиями | Backend 30/30, frontend 20/20, E2E 1/1; [воронки](aspro-pipeline-lifecycle.md), [стадии](aspro-pipeline-stages.md) | IN_PROGRESS |
| CRM | Теги, пользовательские поля, файлы, наблюдатели, UTM, композер активностей | UI: карточка сделки `/_module/crm/view/lead/10?tab=lead_info`, REA `ev_97ac6b8b659b21aceb5b23c1717b735912cd77906caa694178a2be2ab9d17493`; [сценарий](aspro/scenarios/deal-card-v2.md) | P1 | `deal_tags`, `deal_watchers`, `deal_contacts`, `deal_attachments`, `deal_custom_values`, UTM в `deals`; миграция `0011` | `DealDetails.tsx`, тип записи в истории | Backend 42/42, frontend 28/28, E2E 1/1, сборка | TESTED |
| CRM | Источники, причины отказа, фильтры, табличный вид | UI: Kanban, вкладки и фильтры | P1 | Частично | Частично | Частично | SPECIFIED |
| Задачи | CRUD, подзадачи, чек-листы, сроки, исполнители | [Исследование формы и доски](aspro-task-research.md), REA evidence `ev_d8b0862920e64c2c67a1e98e72e75d5ddff6a760fe3796be8597f7b624d9f71c`; [сценарий](aspro/scenarios/tasks-module.md) | P2 | `tasks`, `task_statuses`, `task_checklist_items`, `task_watchers`; миграция `0012`, перенос `deal_tasks` | `Tasks.tsx`: Канбан, Список, карточка, чек-лист, подзадачи, статусы | Backend 45/45, frontend 31/31, E2E 1/1, сборка | TESTED |
| Проекты | CRUD, этапы, команда (без шаблонов и Ганта) | UI `7e96.aspro.cloud`: колонки списка и вкладки карточки, REA `ev_fa114a529f6c7c358f26e4f0f48c5e44d930116357cddf912f64d18e7447f5e5`, `ev_761b20d376adb0852847031c7c065f77d89fd6d80d00f16b0e2678480f661277`; [сценарий](aspro/scenarios/projects-module.md) | P2 | `projects`, `project_stages`, `project_members`, `project_contacts`, `project_events`; `0013`, guards `0015` | `Projects.tsx`: список, вкладки, карточка, команда, события, архив | `test_projects.py`, `Projects.test.tsx`, `e2e/projects.spec.ts`; общий прогон 57/38/3 | TESTED |
| Проекты | Создание проекта из сделки | [Сценарий](aspro/scenarios/projects-module.md): только выигранная сделка, перенос клиента, суммы и контактов, защита от дубля | P2 | `POST /projects`, `force` для повторного создания | Кнопка «Новый проект» с выбором сделки | Backend 48/48, frontend 34/34, E2E 1/1 | TESTED |
| Финансы | Счета, поступления, статусы оплат, организации, акты (без бюджетов/календаря) | UI: «Список счетов», колонки и печатные формы, REA `ev_fa114a529f6c7c358f26e4f0f48c5e44d930116357cddf912f64d18e7447f5e5`; [сценарий](aspro/scenarios/finance-module.md) | P2 | `finance.py`, `0014`; атомарная нумерация, платежи, workspace-FK, OWNER/ADMIN | `Finance.tsx`: список, создание, платежи, акты, печать/PDF | `test_finance.py`, `test_finance_concurrency.py`, `Finance.test.tsx`, `e2e/finance.spec.ts`; общий прогон 57/38/3 | TESTED |
| Документы | Собственная печатная форма счёта; общий конструктор не реализован | UI: «Формы» для счетов, смет и актов, REA `ev_7c633799e67e308e99b897860d40ee3b5fd46e33d731f8477f9eb8cf300d602b`; в объёме P2 только счёт | P2 | Снимки реквизитов в счёте | `Finance.tsx`: браузерная печать/PDF | `Finance.test.tsx`, генерация PDF в `finance.spec.ts`; конструктор не проверен | IN_PROGRESS |
| Коммуникации | Почта, чат, телефония, уведомления | UI: приложения установлены; провайдеры не подключены | P2 | Нет | Нет | Нет | NOT_RESEARCHED |
| Автоматизация | Триггеры, действия, webhooks, n8n | Документированные webhook CRM/задач; собственная ограниченная очередь событий | P2 | `services/webhooks.py`, `0024`, отдельный worker | `Webhooks.tsx` | backend transport/concurrency, frontend, E2E очереди; внешняя доставка не проверена | TESTED в ограниченном объёме |
| Аналитика | Текущие продажи, задачи, проекты; без финансового ядра | UI: вкладки рабочего стола; собственные формулы | P3 | `analytics.py`, SQL-агрегации | `LiveDashboard.tsx`, без демоданных | backend/local dates/currency, frontend, E2E | TESTED в ограниченном объёме |
| Администрирование | Команды, RBAC, аудит, импорт/экспорт | UI: «Команда», «Группы», CSV-импорт; детали не исследованы | P3 | Частично | Частично | Частично | NOT_RESEARCHED |
| Дополнительно | База знаний, Agile, каталог, тайм-трекер, клиентский кабинет, HR, имущество | UI: приложения доступны/установлены; детали не исследованы | P3 | Нет | Нет | Нет | NOT_RESEARCHED |
| Интеграции | Банки, 1С, внешние CRM, рассылки | Каталог 62 приложений; доступы к внешним системам не проверены | P3 | Нет | Нет | Нет | NOT_RESEARCHED |

## Исследование REA

На главной странице портала REA зафиксировал 111 загруженных скриптов, кандидаты маршрутов и 48 кандидатов сетевых адресов. Это статические признаки, не доказательство выполнения всех маршрутов или бизнес-правил. Пассивная инспекция страницы CRM подтвердила форму сделки и поля, отмеченные выше. REA evidence идентификаторы и снимки не содержат пользовательских данных в репозитории.

Повторный проход 23.10.2026 покрыл все разделы верхнего меню и карточки сделки и проекта; каталог функций, Evidence и решения по приоритетам собраны в [инвентаризации](aspro/feature-inventory.md), новые сценарии — в [docs/aspro/scenarios](aspro/scenarios).

## Покрытие

Число строк не является процентом готовности CRM: строки имеют разный объём, многие объединяют несколько функций. Проверки не дают полного соответствия Аспро.Cloud. Исторические числа выше относятся к моменту реализации. Общий срез 24.10.2026: backend 95/95, frontend 68/68 + build, E2E 8/8. CSV и DnD прошли после исправления компоновки и выбора видимой области перетаскивания в браузерном тесте.

### Дополнения 24.10.2026

| Сценарий | Код/миграция | Проверки | Статус |
| --- | --- | --- | --- |
| [Реальные файлы сделки](aspro/scenarios/file-attachments.md) | `attachments.py`, `0016`, `DealDetails.tsx` | backend, frontend, побайтный E2E | TESTED |
| [Календарь задач](aspro/scenarios/task-calendar.md) | `TaskCalendar.tsx`, пагинация | frontend и E2E в Asia/Yekaterinburg | TESTED |
| [Адресные упоминания](aspro/scenarios/mention-notifications.md) | `notifications.py`, `0017`, `Notifications.tsx` | backend, frontend, двухаккаунтный E2E | TESTED |
| [Основной контакт](aspro/scenarios/deal-contact-consistency.md) | `crm.py`, `0018` | backend и заполненная миграция | TESTED |
| [План/Гант проекта](aspro/scenarios/project-work-plan.md) | `project_work.py`, `0019`, `ProjectWorkPlan.tsx` | backend, frontend, E2E | TESTED |
| [Шаблоны плана](aspro/scenarios/project-templates.md) | `project_templates.py`, `0020` | backend rollback, frontend, E2E | TESTED |
| [Входящие заявки](aspro/scenarios/incoming-leads.md) | `integrations.py`, `0021`, `Integrations.tsx` | backend, независимые конкурентные транзакции, frontend, E2E | TESTED |
| [Отдельный раздел клиентов](aspro/scenarios/client-directory-page.md) | `Clients.tsx`, прежние CRUD API | frontend и CRM E2E | TESTED |
| [Учёт времени задач](aspro/scenarios/task-time-tracking.md) | `task_time.py`, `0022`, `TaskTime.tsx` | backend, frontend, независимые старты, E2E | TESTED |
| [Повторение после завершения](aspro/scenarios/task-recurrence.md) | `task_recurrence.py`, `0023`, `TaskRecurrence.tsx` | backend, независимые завершения, frontend, E2E | TESTED |
| [Исходящие webhooks](aspro/scenarios/outgoing-webhooks.md) | `webhooks.py`, `0024`, worker, `Webhooks.tsx` | backend transport/rollback/concurrency, frontend, E2E очереди | TESTED |
| [Живые Dashboard/KPI](aspro/scenarios/live-dashboard.md) | `analytics.py`, `LiveDashboard.tsx` | backend, frontend, E2E | TESTED |
| [CSV-экспорт](aspro/scenarios/csv-export.md) | `exports.py`, `CsvExport.tsx` | backend/frontend, E2E скачивания и регрессия CRM DnD | TESTED |
| [Общий поиск студии](aspro/scenarios/global-search.md) | `search.py`, `GlobalSearch.tsx`, маршруты карточек | пять типов, workspace, literal wildcard, страницы; frontend и E2E переходов | TESTED |

Актуализация после общего поиска: backend 97/97, frontend 74/74 + build, E2E 9/9. Это ограниченный поиск в выбранной студии, не полнотекстовый движок и не подтверждение полного соответствия референсу.

TESTED: [аудит основных изменений сделок](aspro/scenarios/deal-audit.md), `0025`, `DealAudit.tsx` в настройках OWNER/ADMIN. Актуальный общий срез: backend 100/100, frontend 76/76 + build, E2E 10/10. Сохранность автора после отзыва доступа и downgrade/upgrade проверены; усиленный rollback дополнительно 3/3. Это не аудит всех модулей/endpoint.

TESTED только выявление [кандидатов в дубли](aspro/scenarios/duplicate-candidates.md): компании/контакты, причины email/телефон/имя, страницы и точное открытие карточки без изменения данных. Объединение НЕ реализовано. Последний общий срез: backend 103/103, frontend 79/79 + build, E2E 11/11.

## Следующее исследование

Последовательно проверить пользовательские сценарии CRM → задачи → проекты → финансы и затем остальные установленные модули. Для каждого записать поля, права, состояния, связи и отдельный критерий приёмки. Реализацию вести по P0–P3 и по одному сценарию на PR.
