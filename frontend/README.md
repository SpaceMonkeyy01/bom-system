# BOM System front end

React + TypeScript + Vite, Mantine for components, React Query for server state, React Router.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm test           # unit tests
npm run build      # type-check and build to dist/
```

The API must be running (see the root `CLAUDE.md`). To get a login:

```bash
python backend/scripts/create_user.py you@example.com "You" admin
```

`VITE_API_BASE` sets the API origin for a deployed build; leave it unset when the API is on the same origin.

API changes the front end needs are listed in [API_REQUESTS.md](API_REQUESTS.md).
