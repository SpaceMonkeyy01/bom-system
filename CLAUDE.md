# BOM System — working notes for Claude Code

Web app for a sign manufacturer's BOM team. Orders come from Airtable; BOMs are generated from sign-type
templates by a formula engine; materials, stock and rates live in an inventory module fed by iFlow (two
stores, BS and NS, with overlapping numeric ids); costs are written back to the order. Odoo is optional —
its Internal Reference is kept only as an alternate key.

The full spec lives in the Claude project "BOM System - Saad" (doc "BOM System Spec") together with the
as-is analysis of the Google Sheet, the material categorisation workbook and a review of the team's
prototype calculator. Decisions already taken are summarised at the bottom of this file.

## Layout

```
backend/
  app/engine/formula.py   formula language (tokenizer → parser → evaluator, QTY()/COST() cross-line refs)
  app/models/             SQLAlchemy models: core (materials, categories, rates, stock), templates, orders/BOMs
  app/services/rates.py   RateResolver — picks a rate per material via RatePolicy (global/category/material)
  app/services/bom.py     build_bom()/save_bom(): order + template + params → frozen, versioned BOM
  app/services/templates.py  draft/validate/preview/publish/diff for template versions
  app/services/auth.py    JWT, argon2, PERMISSIONS and require(); app/api/auth_routes.py
  app/services/inventory.py  iFlow file import, review queue (link/create), add rates, merge materials
  app/api/inventory_routes.py  /inventory/stock-imports, /inventory/review-queue, /materials/{id}/rates|merge,
                           /rate-policies, /categories, /uoms, /suppliers
  app/api/                FastAPI routes + pydantic schemas (prefix /api)
  app/seed/               loaders from the spreadsheets in data/raw (idempotent): python -m app.seed.run
  scripts/regression_october.py  replays all 555 October sheet blocks through the engine (must stay 100%)
  alembic/                migrations (autogenerate from app.models)
  tests/                  pytest (engine tests; add API/service tests alongside)
data/raw/                 source spreadsheets, git-ignored — ask Saad for them (see data/README.md)
frontend/                 not started: React, Create-BOM flow first
```

## Run

```bash
cd backend
pip install -e ".[dev]"                 # Python 3.12+
cp .env.example .env                    # BOM_DATABASE_URL etc.
alembic upgrade head
python -m app.seed.run                  # needs data/raw/*.xlsx + airtable csv
pytest
python scripts/regression_october.py   # expect: 368/368 exact; --sheet October_Remaining → 187/187
uvicorn app.main:app --reload           # http://localhost:8000/docs
```

Postgres 14+ is required. Dev credentials in `.env.example` (bom/bom). Never commit `data/raw`.

## Conventions

- Formula language must stay byte-compatible with the prototype and BOM_Check.xlsx formulas; any change
  needs a test in `tests/test_formula.py` and a green regression run.
- Materials have app ids; external ids are `MaterialExternalKey(system, store, external_id)`. Never key on
  a bare iFlow id — BS and NS reuse numbers.
- Rates are never overwritten (`MaterialRate` rows accumulate); BOM lines freeze rate, source and date.
- Rates carry a UOM. The resolver prefers a rate in the template line's unit; a line whose only rate is in another
  unit gets a `warning` (not an error). Paint lines are in Gram (the recipes compute grams) even though Odoo
  stocks paint in quarts/gallons — never "fix" that by changing the line unit to the container.
- Templates are versioned; publishing never mutates a saved BOM. Flagged lines (`ComponentLine.notes`)
  are the template owner's to-do list from the import.
- Soft-delete only for anything a saved BOM references.
- Commit messages: imperative subject, body explains why. Run `pytest` before committing.

## Decisions so far

- Stack: FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL; React front end; host on Render.
- Airtable stays the order master (one table per month); the app syncs orders and writes back
  BOM Price (PKR/USD), production cost, box dimension, est. shipment cost, BOM Done.
- iFlow is stock truth; v1 imports the "MAIN STORE STOCK SUMMARY" export per store, API later if one exists.
- Rate sources: `bom` (manual, effective-dated) and `iflow:<store>` (derived from imports); global policy
  prefers `bom`, falls back to `iflow:BS` then `iflow:NS`, flags rates older than 60 days as stale.
- Wastage per cost head (Metal 20 %, Acrylic 20 %, Alucobond 10 %) applied to cost; misc = 10 % of total
  with wastage as one automatic line; USD = PKR/270 × 1.2, production = material / 0.6 (sheet's rules).
- Auth: JWT bearer (`POST /api/auth/login`, OAuth2 password form), argon2 hashes. Roles admin, template_owner,
  bom_editor, inventory_manager, viewer; permissions in `app/services/auth.py::PERMISSIONS`, enforced with
  `Depends(require("bom:write"))` etc. All `/api/*` routes need a user. Dev users: `scripts/create_user.py`.
  First admin can be bootstrapped from `BOM_BOOTSTRAP_ADMIN_EMAIL/PASSWORD`. CORS from `BOM_CORS_ORIGINS`.

## Open items (state in the seeded data)

- Sheet price list is from 2025-09 → all `bom` rates currently stale; team to refresh or prefer iFlow.
- 192 price-list names created as "sheet-only" materials (`review_status=to_review`) pending merge.
- 81 October orders have an Airtable sign type that maps to no `SignType` (23 distinct names).
- 100 Odoo products share an iFlow id with another product; flagged in `Material.notes`.
- 44 of 45 imported templates are drafts with flagged lines; only "Metal - With Backlit" is published.
- iFlow is built by an independent developer; an API can be requested later. Whether the export carries a rate field is unknown.
- Suppliers seeded as names only (75, from the categorisation sheet); supplier rates must be entered by the team.

## Next

1. Frontend: login screen, then Create-BOM flow (order queue → parameter form → live lines → save) against `/api`.
2. Template editor UI (port the prototype's Formulas tab UX) on the editor API: POST /templates/drafts,
   PUT /templates/{id}, POST /templates/validate, POST /templates/{id}/preview, POST /templates/{id}/publish,
   GET /templates/flagged (to-do list), GET /sign-types/unmapped + PATCH /sign-types/{id} (aliases re-map orders).
3. Airtable live sync + write-back (`app/seed/orders.py::map_airtable_record` is the field mapping).
4. Inventory UI: stock upload per store, review queue (suggestions → link / create), material detail with
   rate history + add rate (bom/supplier), merge duplicates, rate policy settings.
5. UOM conversions (e.g. quart → grams by density) so container-priced rates can serve gram lines.
