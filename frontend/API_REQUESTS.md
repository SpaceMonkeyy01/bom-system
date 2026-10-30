# API requests from the front end

The front end doesn't edit `backend/`. These are the changes it would like, with what it does until then.
Nothing here is blocking; no screen uses mock data.

## TODO

### 1. `GET /api/orders`: apply `needs_bom` before `limit`

`list_orders` applies `.limit(limit)` in SQL and filters `needs_bom` in Python afterwards. Orders are sorted oldest
dispatch first, so once the oldest `limit` orders all have BOMs, the queue comes back short or empty even though
newer orders still need one.

- **Asked:** filter in SQL before the limit.
- **For now:** the queue passes `limit=2000`, which only pushes the problem further out.

### 2. `GET /api/materials`: return `cost_tag`

An extra line's cost head decides its wastage and where it rolls up, but the search result doesn't say what a
material's cost head is. With no `cost_tag` the backend files the extra under Misc at 0 % wastage, so a metal
extra would be under-costed.

- **Asked:** add `cost_tag` to `MaterialSearchOut`, derived the way `app/seed/common.py::cost_tag_for_category` does.
- **For now:** extras default to Misc and the user can change the cost head on the row.

### 3. `GET /api/cost-heads`: list the cost heads

The cost-head picker on an extra line needs the options (name, default wastage %).

- **Asked:** a read-only list of `CostHead`.
- **For now:** the picker offers the heads already used by the BOM's lines, plus Misc.

### 4. Order images: Airtable attachment URLs expire

`Order.images` stores the attachment URLs as they were at sync time, and Airtable's signed URLs stop working after
a few hours. Not yet confirmed against real data.

- **Asked:** refresh URLs on sync, or serve attachments through the API.
- **For now:** a broken image falls back to a placeholder and the file name stays visible.
