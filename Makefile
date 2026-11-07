.PHONY: setup services backend frontend test lint typecheck check

setup:  ## install all dependencies
	cd backend && uv sync
	cd frontend && npm ci

services:  ## start Redis in Docker
	docker compose up -d

backend:  ## API on :8000 (ASGI, autoreload)
	cd backend && uv run uvicorn config.asgi:application --reload --port 8000

frontend:  ## UI on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

test:
	cd backend && uv run pytest
	cd frontend && npx vitest run --passWithNoTests

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy .
	cd frontend && npx tsc -b

check: lint typecheck test  ## everything CI runs
