.PHONY: up down dev-api dev-web demo test lint audit

up:            ## full stack in Docker
	docker compose up --build

down:
	docker compose down

dev-api:       ## API on :8000 with live Yahoo/FRED data, SQLite
	cd backend && uvicorn app.main:app --reload --port 8000

demo:          ## API on offline synthetic data (no internet needed)
	cd backend && DATA_PROVIDER=synthetic uvicorn app.main:app --reload --port 8000

dev-web:       ## Next.js on :3000, proxies /api to :8000
	cd frontend && npm run dev

test:
	cd backend && python -m pytest -q
	cd frontend && npm run typecheck

audit:
	cd backend && pip-audit -r requirements.txt
	cd frontend && npm audit
