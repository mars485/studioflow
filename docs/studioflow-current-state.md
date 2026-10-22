# StudioFlow: текущее состояние

Проверено по локальному коду 23.10.2026. Это аудит реализации, а не подтверждение production.

## Архитектура

- Backend: FastAPI, SQLAlchemy AsyncSession, PostgreSQL, Alembic; код в `backend/app`.
- Frontend: React, TypeScript, Vite; код в `frontend/src`.
- Данные: `User`, `Workspace`, `WorkspaceMember`, `AuthSession`, `AuthThrottle`, `Client`, `Pipeline`, `PipelineStage`, `Deal` в `backend/app/models/entities.py`.
- Миграции: `0001_initial_schema`, `0002_crm_follow_up`, `0003_auth_sessions`.
- Проверки: backend pytest, frontend Vitest и сборка, Playwright E2E в `frontend/e2e/crm.spec.ts`, CI в `.github/workflows/p0-checks.yml`.

## Готово в коде

| Область | Реализация | Ограничение |
| --- | --- | --- |
| Доступ | Регистрация, вход, выход, серверная cookie-сессия, роли OWNER/ADMIN/MANAGER, membership | Нет подтверждения email, восстановления пароля и гибкого RBAC |
| Рабочие пространства | Создание, переименование, участники и роли | Нет команд и произвольных прав |
| Клиенты | Список и создание в пределах workspace | Нет отдельной карточки и полного CRUD контактов/компаний |
| Сделки | CRUD, воронка и стадии, Kanban, поиск, сумма, источник, описание | Нет истории действий, тегов, пользовательских полей, вложений и табличного вида |
| Follow-up | Одно текущее действие на сделку, фильтр на сегодня | Нет истории завершённых действий и уведомлений |
| Защита данных | Workspace scoped API, проверки связей, ограничения БД | Новые сущности должны повторять эти правила |

## Демонстрационные или отсутствующие функции

Dashboard, проекты, задачи, финансы и аналитика в `frontend/src/App.tsx` демонстрационные. Для них нет соответствующих моделей, миграций и workspace scoped CRUD API. Документы, коммуникации, автоматизации, интеграции и база знаний также не реализованы как рабочие модули.

## Проверка

Предыдущий изолированный запуск 22.10.2026: backend 24 теста, frontend тесты/сборка и один Playwright E2E прошли. Это исторический результат текущего чата. При проверке 23.10.2026 Docker daemon недоступен (`dockerDesktopLinuxEngine`), поэтому backend/PostgreSQL и E2E повторно не проверены. Fallback из `AGENTS.md`: `npm ci`, `npm run test` (13/13) и `npm run build` прошли. Production и пользовательские данные не затрагивались.

## Следующий срез

P1 по `docs/REFERENCES.md`: карточка сделки v2, начиная с сохранённой ленты активностей с автором и временем. Для новой сущности нужны миграция, workspace scoped API, авторизация, UI-состояния и тесты.
