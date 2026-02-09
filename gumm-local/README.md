# gumm-local

Neighborhood loyalty hub for cafes to track regulars, run reward loops (for example, buy 9 get 10 free), and mark VIP locals.

## Stack

- Backend: FastAPI + asyncpg (`gumm-local/server`)
- Frontend: React + Vite (`gumm-local/client`)
- Database: PostgreSQL tables prefixed with `local_`

## Local Development

### Backend

```bash
cd gumm-local/server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:password@localhost:5432/matcha"
export GUMM_LOCAL_PORT=8004
python run.py
```

### Frontend

```bash
cd gumm-local/client
npm install
npm run dev
```

Frontend runs on `http://localhost:5176` and proxies `/api` to backend `http://localhost:8004`.

## Core API Endpoints

- `GET /api/cafes` / `POST /api/cafes`
- `GET /api/cafes/{cafe_id}/programs` / `POST /api/cafes/{cafe_id}/programs`
- `GET /api/cafes/{cafe_id}/locals` / `POST /api/cafes/{cafe_id}/locals`
- `PATCH /api/cafes/{cafe_id}/locals/{local_id}` (toggle VIP and update local details)
- `POST /api/cafes/{cafe_id}/locals/{local_id}/visits` (stamp a visit)
- `GET /api/cafes/{cafe_id}/locals/{local_id}/progress` (reward progress)
- `POST /api/cafes/{cafe_id}/locals/{local_id}/redeem` (redeem available reward)
- `GET /api/cafes/{cafe_id}/dashboard` (summary metrics)

## Docker + Deploy

- Backend image: `gumm-local-backend`
- Frontend image: `gumm-local-frontend`
- Compose services: `gumm-local-backend`, `gumm-local-frontend`
- Ports: `8004` (API), `8084` (frontend)

Build and push with existing root script:

```bash
./build-and-push.sh --gumm-local
```

Deploy on EC2 with existing updater:

```bash
./update-ec2.sh --gumm-local
```
