# StudioFlow

CRM/ERP для веб-студий: продажи, клиенты, проекты, задачи и финансы в одном рабочем пространстве.

## Реализовано

CRM работает с FastAPI и PostgreSQL, без mock-сделок:

- список, создание, просмотр, редактирование и удаление сделок;
- Kanban со стадиями из API, drag-and-drop с сохранением стадии;
- выбор рабочего пространства и воронки, поиск по сделке/клиенту/контакту;
- создание клиента или выбор существующего при создании сделки;
- сумма с точностью до копеек, контактное лицо, источник, описание;
- Follow-up: дата/время, действие, комментарий, изменение и удаление;
- загрузка, пустые состояния, ошибки, повторная загрузка и блокировка повторного сохранения;
- фильтр Follow-up на сегодня и выделение просроченных контактов;
- проверка membership и связей workspace → клиент / воронка → стадия;
- миграции, backend-тесты на PostgreSQL и frontend-тесты.

Карточка и счётчики обновляются после успешного ответа API. При ошибке переноса сделка остаётся в исходной стадии, при ошибке формы введённые данные сохраняются. После перезагрузки CRM читает данные из базы.

Dashboard, проекты, задачи, финансы и аналитика пока остаются демонстрационными экранами. История коммуникаций и задачи в карточке сделки ещё не реализованы; фиктивные записи из CRM убраны.

## Архитектура

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 AsyncSession, asyncpg, PostgreSQL 16, Alembic, Pydantic.
- Frontend: React, TypeScript, Vite, Lucide, CSS; Vitest и Testing Library для тестов.
- `backend/app/api/dependencies.py`: текущий пользователь и проверка доступа к workspace.
- `backend/app/api/v1/crm.py`: REST API, scoped-запросы и проверка связей.
- `backend/app/api/v1/schemas.py`: входные/выходные схемы и валидация.
- `backend/app/models/entities.py`: модели; `backend/alembic/versions/`: миграции.
- `frontend/src/api.ts`: типы, обработка HTTP-ошибок, загрузка всех страниц списка.
- `frontend/src/CRM.tsx`: доска, формы и карточка; `App.tsx`: оболочка и Dashboard.

Сделка ссылается на клиента, воронку и стадию через UUID. Составные внешние ключи в PostgreSQL дополнительно запрещают связи между разными workspace и стадию чужой воронки. Каждое чтение/изменение сделки ограничено `workspace_id`. Чужой или отсутствующий workspace/объект возвращает 404.

Follow-up хранится в сделке как одно текущее следующее действие (`follow_up_at`, `follow_up_action`, `follow_up_comment`), а не журнал активностей. Время — PostgreSQL `timestamptz`. API требует ISO 8601 с часовым поясом; браузер отправляет UTC и показывает время в часовом поясе устройства. Фильтр «сегодня» также использует пояс устройства. Денежные значения — `Numeric(14,2)` / Decimal; API возвращает их строками.

### Локальная идентификация и workspace isolation

JWT пока не реализован. По умолчанию `DEV_AUTH_ENABLED=false`: CRM API отвечает 401. Для локальной разработки `.env.example` явно включает dev-режим: все запросы выполняются от `DEV_USER_ID`, заданного сервером. Передача user ID в HTTP-заголовке не поддерживается. Доступ разрешён только к workspace, где этот пользователь состоит в `WorkspaceMember`.

Это локальный режим одного пользователя, а не авторизация для публичного сервера. Docker публикует API и Vite только на `127.0.0.1`. Перед публичным развёртыванием нужны JWT/session auth, управление членством и production-конфигурация; одного изменения `SECRET_KEY` недостаточно.

## Запуск через Docker

```powershell
git clone https://github.com/mars485/studioflow.git
cd studioflow
Copy-Item .env.example .env
docker compose up --build
```

В Linux/macOS используйте `cp .env.example .env`. Не добавляйте `.env` и реальные секреты в Git.

При старте API выполняет `alembic upgrade head`, затем `python -m app.seed`. В dev-режиме seed однократно создаёт локального пользователя, workspace StudioFlow и воронку с четырьмя стадиями. Клиентов и сделок он не создаёт. Повторный запуск не дублирует данные. Для пользовательской базы заполните пользователей, membership, воронки и стадии административным способом: CRUD этих справочников пока ограничен.

- Frontend: http://localhost:5173/
- API / Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

Bind mounts, Vite HMR и Uvicorn `--reload` сохранены. Запросы браузера `/api` проходят через Vite proxy к `http://api:8000`; Docker задаёт `API_PROXY_TARGET`. Прямой CORS-доступ браузера к API не требуется.

### Обновление существующей установки

Добавьте в существующий `.env` значения `DEV_AUTH_ENABLED=true` и `DEV_USER_ID=00000000-0000-0000-0000-000000000001` для локального dev-режима. Не перезаписывайте остальные настройки и пароли.

```powershell
git pull
docker compose up --build -d
docker compose exec frontend npm ci
docker compose restart frontend
```

`npm ci` обновляет зависимости в уже существующем volume `frontend_node_modules`. Новые установки получают их при сборке образа. Изменения Python/TSX/CSS подхватываются автоматически; миграции при одном лишь reload не запускаются:

```powershell
docker compose exec api alembic upgrade head
```

Миграция `0002` добавляет nullable-поля к существующим сделкам, сохраняя прежние данные, и включает ограничения суммы и связей workspace. Если в старой базе уже есть отрицательные суммы или некорректные межпространственные связи, миграция остановится: исправьте данные перед повтором. Downgrade до `0001` удаляет новые поля и значения Follow-up, но сохраняет основные сделки. Перед миграцией рабочей базы сделайте резервную копию.

## Frontend отдельно

Нужен Node.js 22.12+ и запущенный backend:

```powershell
cd frontend
npm ci
npm run dev
```

Локальный Vite по умолчанию проксирует `/api` к `http://localhost:8000`. Для другого адреса задайте `API_PROXY_TARGET` в окружении процесса Vite. В production сервер статики должен проксировать `/api` к FastAPI: Vite dev proxy в сборку не входит.

```powershell
npm run test
npm run build
```

## REST API

Общий префикс: `/api/v1`. `{workspace_id}` — UUID доступного рабочего пространства; получить его можно через `GET /workspaces`.

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/health` | Проверка приложения |
| GET | `/workspaces` | Рабочие пространства текущего пользователя |
| GET | `/workspaces/{workspace_id}/pipelines` | Активные воронки со стадиями по порядку |
| GET / POST | `/workspaces/{workspace_id}/clients` | Список / создание клиента |
| GET | `/workspaces/{workspace_id}/deals` | Список: `pipeline_id`, `limit` (1–500, по умолчанию 100), `offset` |
| POST | `/workspaces/{workspace_id}/deals` | Создание сделки, 201 |
| GET / PATCH / DELETE | `/workspaces/{workspace_id}/deals/{deal_id}` | Чтение / частичное изменение / удаление (204) |
| PUT / DELETE | `/workspaces/{workspace_id}/deals/{deal_id}/follow-up` | Сохранение / очистка Follow-up |

Создание сделки:

```json
{
  "title": "Разработка сайта",
  "client_id": "UUID клиента",
  "pipeline_id": "UUID воронки",
  "stage_id": "UUID стадии",
  "amount": "65000.25",
  "contact_name": "Мария",
  "source": "Сайт",
  "description": "Лендинг агентства"
}
```

Для переноса достаточно `PATCH` с `{"stage_id":"UUID новой стадии"}`. При смене воронки передайте согласованные `pipeline_id` и `stage_id` вместе. Валюта новой сделки берётся из workspace. Отрицательные суммы, более двух десятичных знаков, пустое название и `null` для обязательных полей отклоняются (422). Неизвестные входные поля тоже отклоняются; `workspace_id` нельзя изменить через тело запроса.

Сохранение Follow-up:

```json
{
  "at": "2026-12-01T16:30:00+05:00",
  "action": "proposal",
  "comment": "Отправить коммерческое предложение"
}
```

Действия: `call`, `message`, `proposal`, `decision`. PUT заменяет текущее действие целиком; DELETE очищает все три поля. Подробные схемы доступны в Swagger.

## Проверки

Полная проверка в изолированной PostgreSQL без портов и production volumes:

```powershell
docker compose -p studioflow-crm-check -f docker-compose.test.yml run --build --rm backend
docker compose -p studioflow-crm-check -f docker-compose.test.yml run --build --rm --no-deps frontend
docker compose -p studioflow-crm-check -f docker-compose.test.yml down
```

Backend-команда применяет миграции, выполняет `alembic check` и pytest. Проверяются CRUD, денежная точность, Follow-up, часовые пояса, workspace isolation, принадлежность стадии воронке, валидация и ограничения БД. Отдельный тест создаёт временную базу, проверяет сохранность старой сделки при upgrade/downgrade и повторный seed. Поэтому тестовой PostgreSQL нужен CREATE DATABASE; используйте только отдельную тестовую БД.

Для запуска pytest без Docker задайте `TEST_DATABASE_URL` и `DATABASE_URL` на мигрированную тестовую PostgreSQL. Без `TEST_DATABASE_URL` интеграционные тесты пропускаются, выполняется health-тест.

Frontend-тесты проверяют загрузку и повтор после ошибки, создание/редактирование/удаление, сохранение и восстановление Follow-up, сохранение черновика при ошибке и перенос Kanban с неуспешным/успешным ответом API.

## Roadmap

1. JWT/session auth, пользователи, роли и управление membership.
2. Полный CRUD клиентов, контактов, воронок и стадий.
3. История коммуникаций и изменений, несколько активностей на сделку.
4. Реальные показатели Dashboard и уведомления Follow-up.
5. Проекты и создание проекта из успешной сделки.
6. Задачи, дедлайны и учёт времени.
7. Финансы, платежи и аналитика.
8. Production Docker, развёртывание и резервные копии.