# BOM System

Web app for the BOM team: orders from Airtable → BOM generated from sign-type templates with a formula engine → materials, stock and rates in an inventory module fed by iFlow → costs written back to the order.

Spec: see the project doc "BOM System Spec". Decisions log and as-is analysis live in the Claude project.

## Layout

```
backend/   FastAPI + SQLAlchemy + Alembic (Python 3.12+), formula engine, seed scripts
frontend/  React app (phase 1b)
data/      sample/seed inputs (raw spreadsheets are not committed; see data/README.md)
```

## Backend quick start

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env            # edit DB URL if needed
alembic upgrade head
pytest
uvicorn app.main:app --reload
```

Requires PostgreSQL 14+. Default URL: `postgresql+psycopg://bom:bom@localhost:5432/bom`.

## Deploy (Render)

`render.yaml` is a Render Blueprint: **Dashboard → New → Blueprint → this repo**. It creates a Postgres
database, the API (`bom-api`, runs `alembic upgrade head` before each deploy), the static front end (`bom-web`)
and a 15-minute cron that pulls orders from Airtable and retries failed write-backs.

After the first deploy, set in the Render dashboard:

- `bom-api`: `BOM_BOOTSTRAP_ADMIN_EMAIL` / `BOM_BOOTSTRAP_ADMIN_PASSWORD` (first admin, created on first start),
  `BOM_CORS_ORIGINS` to the `bom-web` URL, and the Airtable vars when you have a token.
- `bom-web`: `VITE_API_BASE` to the `bom-api` URL (then redeploy the static site).

Seeding production: run `python -m app.seed.run` once from the API service's shell with the four source files
copied to `backend/data/raw/` (or seed a local database and `pg_dump | psql` it to Render).

Never set `BOM_JWT_SECRET` by hand — the blueprint generates it.
