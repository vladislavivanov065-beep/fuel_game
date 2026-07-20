# Войны заправок (Gas Station Wars)

Браузерная многопользовательская экономическая стратегия. Технические детали: [TECHNICAL_SPEC.md](./TECHNICAL_SPEC.md).

Текущий этап разработки: **Этап 13 — деплой на Railway**.

## Стек

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL
- Frontend: React, TypeScript, Vite, TanStack Query, Zustand

Redis и Docker в проекте не используются: сессии авторизации хранятся в PostgreSQL
(таблица `sessions`), а фоновый планировщик тика игры работает как asyncio-задача
внутри того же процесса FastAPI (см. `backend/app/simulation/scheduler.py`).

## Локальный запуск

Нужен только PostgreSQL (например `postgres:16`, поднятый локально или в отдельном контейнере).

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # при необходимости отредактируйте значения
alembic upgrade head
python -m scripts.import_osm        # станции из data/mari_el_stations.geojson
python -m scripts.seed_game_data    # НПЗ
python -m scripts.build_road_graph  # дорожный граф из data/mari_el_roads.geojson
uvicorn app.main:app --reload
```

Backend поднимется на `http://localhost:8000`, health-check: `GET /api/health`.

Три сид-команды идемпотентны — их безопасно перезапускать. Их также можно
выполнить одной командой через `python -m scripts.release` (сначала
`alembic upgrade head`, затем все три скрипта по очереди). На Railway это же
происходит автоматически при каждом запуске — миграции и сиды выполняются
внутри `lifespan` самого FastAPI-приложения (`app/core/release.py`), а не как
отдельная pre-deploy команда, поэтому не зависят от того, как платформа
резолвит путь до отдельного интерпретатора/venv.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend поднимется на `http://localhost:5173`.

## Проверки качества

### Backend

```bash
cd backend
ruff check .
ruff format --check .
mypy app
pytest
```

### Frontend

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

## Переменные окружения

См. `backend/.env.example` и `frontend/.env.example`.

## Деплой на Railway

Backend и frontend — два отдельных Railway-сервиса в одном монорепозитории, плюс
управляемый PostgreSQL (Redis не нужен). Отдельного worker-сервиса нет: фоновый
тик игры выполняется как asyncio-задача внутри процесса backend-сервиса.

Для каждого сервиса в настройках Railway нужно указать:

- **Root Directory**: `backend` (или `frontend`);
- **Config File Path**: `railway.json` относительно Root Directory — используется
  builder `RAILPACK` и `startCommand`/`healthcheckPath` из `backend/railway.json` /
  `frontend/railway.json`.

Переменные окружения:

- backend: `DATABASE_URL` (Railway подставляет автоматически при подключении
  Postgres-плагина; префикс `postgres://`/`postgresql://` без драйвера
  нормализуется в `postgresql+asyncpg://` в `app/core/config.py`), `CORS_ORIGINS`
  (публичный URL frontend-сервиса), `SESSION_COOKIE_SECURE=true` (backend и
  frontend на разных поддоменах Railway — нужен `SameSite=None`, а он требует
  `Secure=true`), `LOG_LEVEL`.
- frontend: `VITE_API_URL` (публичный URL backend-сервиса). `vite.config.ts`
  уже разрешает `preview.allowedHosts: ['.up.railway.app']` — Railway выдаёт
  новый случайный поддомен на каждый деплой.

При каждом старте backend-процесса (в `lifespan`, до открытия порта) автоматически
выполняются `alembic upgrade head` и все сид-скрипты (`app/core/release.py`) —
отдельная pre-deploy команда не требуется и не настроена. Данные станций, НПЗ и
дорожного графа хранятся в PostgreSQL и переживают редеплой без volume; исходные
GeoJSON-файлы для сидов лежат в репозитории (`backend/data/`).

Health-check: `GET /api/health` (проверяет доступность БД) — указан как
`healthcheckPath` в `backend/railway.json`, Railway ждёт его перед переключением
трафика на новый деплой.
