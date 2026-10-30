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
