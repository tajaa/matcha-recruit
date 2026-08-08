# oceanlab

Digital label platform: master ingestion, catalog data, packaging/delivery,
and royalty/registration file generation. FastAPI + PostgreSQL server,
React + Vite client. See `PROJECT.md` for the full design.

## Server setup

```bash
docker exec matcha-postgres createdb -U matcha oceanlab
docker exec matcha-postgres createdb -U matcha oceanlab_test

cd server
cp .env.example .env
# edit .env: DATABASE_URL against matcha-postgres, OCEANLAB_TOKEN

uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Run the test suite (uses `oceanlab_test`, migrated fresh each session):

```bash
cd server
uv run pytest
```

## Client setup

```bash
cd client
npm install
npm run dev
```

The dev server proxies `/api` to `127.0.0.1:8000` — no CORS config needed.
