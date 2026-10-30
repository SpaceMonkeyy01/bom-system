# API requests from the front end

The front end doesn't edit `backend/`. These are the changes it would like, with what it does until then.
Nothing here is blocking; no screen uses mock data.

## TODO

### 1. `needs_bom` and the dashboard count should leave out orders done in Airtable

Found on the real October data: 468 of the 474 orders `needs_bom=true` returns have `airtable_bom_done` set, 307 of
them already shipped. They were costed in the old sheet, so they don't need a BOM here, but `needs_bom` only looks at
BOMs saved in this app. `/dashboard/summary`'s `orders_awaiting_bom` counts them the same way.

- **Asked:** exclude `airtable_bom_done` from `needs_bom=true` and from `orders_awaiting_bom`.
- **For now:** `lib/orders.ts` filters them out in the browser, which means asking for `limit=2000` so the API's limit
  can't cut orders off before the filter. The Awaiting BOM card counts that same list and ignores the summary's number.

### 2. Decide which statuses need no BOM

Of the 6 orders left in the queue, one is `Cancelled` and one is `Move To China`. If those should never be costed,
`needs_bom` should exclude them too. This one needs an answer from the BOM team.

### 3. Seeded templates: defaults of 1.0, and every number input required

`app/seed/templates.py` sets `required` on every number parameter, so the flag doesn't say which inputs really matter.
Many parameters also default to `1.0` (7 of 8 number inputs on the one published template). A BOM saved without
touching them gets a plausible but wrong total, with no error.

- **Asked:** template owners should clear placeholder defaults and set `required` properly. Worth doing in the seed or
  as part of publishing.
- **For now:** untouched defaults show in orange italics, and a blank required input blocks Save.

## Done (backend)

- `needs_bom` is applied in SQL before the limit (EXISTS on saved BOMs).
- `GET /api/materials` returns `cost_tag` and `rate_uom`; extras now start under the material's own cost head.
- `GET /api/cost-heads` lists heads with `default_wastage_pct`; the picker on extras uses it.
- `GET /api/orders/{id}/images/{index}?thumb=true|false` proxies attachments and refreshes expired Airtable links when
  a token is configured. It needs the bearer token, so it can't be an `<img src>`: `lib/useOrderImage.ts` fetches
  through the API client instead, and only for thumbnails that have been on screen. Without a token expired links
  404 and the placeholder shows, which is what happens with the CSV-seeded data (every sampled URL returned 410).
