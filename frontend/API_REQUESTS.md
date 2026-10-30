# API requests from the front end

The front end doesn't edit `backend/`. These are the changes it would like, with what it does until then.
Nothing here is blocking; no screen uses mock data.

## TODO

### 4. Decide which statuses need no BOM

Cancelled orders are excluded now. Of the orders left in the queue, several have a `Check profit, Decision Pending`
status; whether those should be costed before the decision is for the BOM team.

## Done (backend)

- `needs_bom` is applied in SQL before the limit, excludes orders done in Airtable and cancelled ones.
- `GET /api/materials` returns `cost_tag` and `rate_uom`; extras and new template lines start under the material's
  own cost head.
- `GET /api/cost-heads` lists heads with `default_wastage_pct`; the pickers use it.
- `GET /api/orders/{id}/images/{index}?thumb=true|false` proxies attachments and refreshes expired Airtable links when
  a token is configured. It needs the bearer token, so it can't be an `<img src>`: `lib/useOrderImage.ts` fetches
  through the API client instead, and only for thumbnails that have been on screen. Without a token expired links
  404 and the placeholder shows.
- Imported BOM dates use the Airtable order date; placeholder `1.0` defaults are gone from the seeded templates.
- Template editor API (`/templates/drafts`, `PUT /templates/{id}`, `/validate`, `/publish`, `/preview`, `/flagged`,
  `/sign-types/unmapped`, `PATCH /sign-types/{id}`) and BOM recalculation (`/boms/{id}/rate-changes`,
  `/recalculate`, `/recalculate/save`) are wired up in the UI.
- `POST /templates/{id}/preview` takes an optional `draft` (same shape as `PUT /templates/{id}`) and previews that
  instead of the stored template — nothing is written, so the editor can call it on every edit (debounced like
  `/validate`). It no longer needs `template:write`; any user can preview. Lines from an unsaved draft come back with
  `component_line_id: null`.
- `GET /templates/{a}/diff/{b}` keys lines as `"<material name>|<usage>|<seq>"` (resolved name, falling back to the
  hint, then "(no material)").
- `GET /templates/flagged` returns the resolved material name in `material` (hint as fallback) plus `material_id`.
