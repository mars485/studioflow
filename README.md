# StudioFlow

**StudioFlow** — CRM/ERP-система для веб-студий и небольших digital-команд. Она объединяет продажи, клиентов, проекты, задачи и финансы в одном рабочем пространстве.

Основной бизнес-процесс:

```text
Новая заявка → Сделка → Продажа → Проект → Задачи → Оплата
```

## Возможности

В целевой версии StudioFlow будут доступны:

- CRM с несколькими воронками продаж;
- Kanban-доска сделок;
- карточки клиентов и контактных лиц;
- планирование звонков, встреч и следующих действий;
- история изменений по каждой сделке;
- автоматическое создание проекта из успешной сделки;
- этапы проектов, задачи и подзадачи;
- учёт рабочего времени;
- счета, платежи и расходы;
- расчёт прибыли и маржинальности проектов;
- Dashboard с ключевыми показателями студии.

## Текущая версия

В версии `0.1` подготовлен запускаемый каркас backend:

- FastAPI-приложение;
- асинхронное подключение к PostgreSQL;
- SQLAlchemy 2;
- Alembic и начальная миграция базы данных;
- Docker Compose;
- модели `User`, `Workspace`, `WorkspaceMember`, `Client`, `Pipeline`, `PipelineStage` и `Deal`;
- изоляция данных организаций через `workspace_id`;
- endpoint проверки состояния API;
- базовый автоматический тест.

## Технологии

### Backend

- Python 3.12;
- FastAPI;
- SQLAlchemy 2;
- Alembic;
- Pydantic Settings;
- PostgreSQL 16;
- Uvicorn.

### Frontend — следующий этап

- Next.js;
- TypeScript;
- Tailwind CSS;
- shadcn/ui.

### Инфраструктура

- Docker;
- Docker Compose;
- REST API;
- JWT-авторизация — следующий этап.

## Структура проекта

```text
studioflow/
├── backend/
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── core/
│   │   ├── models/
│   │   └── main.py
│   ├── tests/
│   ├── Dockerfile
│   ├── alembic.ini
│   └── requirements.txt
├── .env.example
├── .gitignore
└── docker-compose.yml
```

## Локальный запуск

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/mars485/studioflow.git
cd studioflow
```

Репозиторий приватный, поэтому GitHub запросит авторизацию.

### 2. Создайте файл окружения

Linux и macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Перед использованием в интернете обязательно замените значение `SECRET_KEY` в `.env` на длинную случайную строку.

### 3. Запустите контейнеры

```bash
docker compose up --build
```

При запуске будут созданы контейнеры API и PostgreSQL, а Alembic применит миграции базы данных.

### 4. Проверьте работу

- Swagger UI: http://localhost:8000/docs
- Проверка API: http://localhost:8000/api/v1/health

Ожидаемый ответ health endpoint:

```json
{
  "status": "ok",
  "service": "StudioFlow API"
}
```

## Полезные команды

Остановить проект:

```bash
docker compose down
```

Остановить проект и удалить локальные данные PostgreSQL:

```bash
docker compose down -v
```

Посмотреть журналы API:

```bash
docker compose logs -f api
```

Применить миграции вручную:

```bash
docker compose run --rm api alembic upgrade head
```

Запустить тесты:

```bash
docker compose run --rm api pytest
```

## План развития

1. Регистрация пользователя и создание Workspace.
2. JWT-авторизация.
3. Автоматическое создание стандартной CRM-воронки.
4. CRUD клиентов и контактных лиц.
5. CRUD сделок и смена этапов Kanban.
6. Активности и следующие действия.
7. Создание проекта из успешной сделки.
8. Frontend на Next.js.
9. Задачи, финансы и аналитика.

## Статус

Проект находится на ранней стадии разработки. Текущая версия предназначена для локального запуска и дальнейшего поэтапного развития MVP.
