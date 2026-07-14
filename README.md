# Войны заправок (Gas Station Wars)

Браузерная многопользовательская экономическая стратегия. Технические детали: [TECHNICAL_SPEC.md](./TECHNICAL_SPEC.md).

Текущий этап разработки: **Этап 0 — базовая инфраструктура** (FastAPI health-check, React health-check страница, Docker Compose).

## Стек

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL
- Frontend: React, TypeScript, Vite, TanStack Query, Zustand

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
`alembic upgrade head`, затем все три скрипта по очереди) — это же используется
как pre-deploy команда на Railway (см. `backend/railway.json`).

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
