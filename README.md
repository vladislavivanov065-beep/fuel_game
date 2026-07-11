# Войны заправок (Gas Station Wars)

Браузерная многопользовательская экономическая стратегия. Технические детали: [TECHNICAL_SPEC.md](./TECHNICAL_SPEC.md).

Текущий этап разработки: **Этап 0 — базовая инфраструктура** (FastAPI health-check, React health-check страница, Docker Compose).

## Стек

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL, Redis
- Frontend: React, TypeScript, Vite, TanStack Query, Zustand

## Локальный запуск (без Docker)

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # при необходимости отредактируйте значения
alembic upgrade head
uvicorn app.main:app --reload
```

Backend поднимется на `http://localhost:8000`, health-check: `GET /api/health`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend поднимется на `http://localhost:5173`.

## Запуск через Docker Compose

```bash
docker compose up --build
```

Поднимает PostgreSQL, Redis, backend (`:8000`) и frontend (`:5173`).

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
