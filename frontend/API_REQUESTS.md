# API requests from the front end

The front end doesn't edit `backend/`. These are the changes it would like, with what it does until then.
Nothing here is blocking; no screen uses mock data.

## TODO

### 1. `POST /templates/{id}/preview` should accept the draft body, and be readable

The preview runs the template as stored, so the editor has to save before the preview reflects an edit. A truly
live preview needs the endpoint to take `{parameters, lines}` like `/templates/validate` does (or a
`POST /templates/preview` sibling). It also requires `template:write`, so viewers get a 403 and the editor hides the
panel for them, although a read-only look at what a published template produces would be useful to anyone.

- **For now:** the panel is labelled "shows the saved draft — save to refresh"; Ctrl/Cmd+S saves. Hidden for roles
  without `template:write`.

### 2. Template diff keys should carry the material name

`template_diff` keys lines by `material_name_hint or material_id`, and the hint is empty for materials matched at
import, so the versions page lists changes as "1 · Front Face" (a material id) or "(no material)".

- **Asked:** key by the resolved material name (and keep the id to disambiguate).
- **For now:** shown as returned.

### 3. `GET /templates/flagged`: `material` is the hint only

For a flagged line whose material did resolve, `material` comes back `null` (it reads `material_name_hint`), so the
to-do list shows "?" for it.

- **Asked:** fall back to the material's name.
- **For now:** "?".

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
