# StudioFlow

**StudioFlow** — CRM/ERP-система для веб-студий и небольших digital-команд. Она объединяет продажи, клиентов, проекты, задачи и финансы в одном рабочем пространстве.

Основной бизнес-процесс:

```text
Новая заявка → Сделка → Follow-up → Продажа → Проект → Задачи → Оплата
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

### Frontend

- React;
- TypeScript;
- Vite;
- CSS;
- Lucide React.

Уже реализованы Dashboard, CRM/Kanban, карточки сделок, боковая карточка сделки, история взаимодействий, задачи и редактор Follow-up. На текущем этапе frontend использует mock-данные; далее интерфейс будет подключён к REST API.

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
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── styles.css
│   ├── index.html
│   ├── package.json
│   └── tsconfig.json
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

## Запуск frontend

Для frontend требуются **Node.js LTS** и **npm**. npm устанавливается вместе с Node.js.

Официальная страница загрузки Node.js: https://nodejs.org/en/download

После установки перезапустите терминал и проверьте версии:

```powershell
node --version
npm --version
```

### Windows PowerShell

Из корневой папки StudioFlow:

```powershell
cd frontend
npm install
npm run dev
```

После запуска Vite выведет локальный адрес приложения, обычно `http://localhost:5173/`.

Если PowerShell сообщает, что `npm.ps1` не может быть загружен из-за запрета выполнения сценариев, разрешите локальные сценарии для текущего пользователя:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Затем перезапустите PowerShell и снова выполните:

```powershell
npm install
npm run dev
```

### Linux / macOS

```bash
cd frontend
npm install
npm run dev
```

### Production-сборка

```bash
npm run build
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

## Ключевая концепция CRM

Одна из центральных функций StudioFlow — **Follow-up**. Активная сделка должна иметь понятное следующее действие: дату и время, тип действия и комментарий. Dashboard должен отвечать менеджеру на вопрос: **«С кем нужно связаться сегодня?»**

## План развития

1. Drag-and-drop сделок между стадиями Kanban.
2. Создание и редактирование сделки.
3. Сохранение Follow-up.
4. CRUD API клиентов, сделок и активностей.
5. Подключение frontend к FastAPI.
6. JWT-авторизация и Workspace.
7. История коммуникаций.
8. Проекты и создание проекта из успешной сделки.
9. Задачи и дедлайны.
10. Финансы и аналитика.
11. Production Docker-конфигурация и развёртывание.

## Статус

Проект находится в активной разработке. Backend-каркас и первая интерактивная версия frontend уже реализованы. Следующий этап — сделать CRM изменяемой и связать интерфейс с FastAPI.
