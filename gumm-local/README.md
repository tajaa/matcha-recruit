# gumm-local

Neighborhood loyalty hub for cafes to register a business, onboard team members, manage regular rewards, and run local email campaigns.

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
export GUMM_LOCAL_JWT_SECRET_KEY="replace_with_a_long_secret"
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

All business routes are bearer-token protected after registration/login.

### Auth and onboarding
- `POST /api/auth/register-business`
- `POST /api/auth/login`
- `GET /api/auth/me`

### Business admin
- `GET /api/business/profile`
- `PATCH /api/business/settings`
- `GET /api/business/team`
- `POST /api/business/team`
- `GET /api/business/media`
- `POST /api/business/media` (multipart upload for images/videos)
- `PATCH /api/business/media/{media_id}`
- `DELETE /api/business/media/{media_id}`

### Cafes, rewards, and locals
- `GET /api/cafes` / `POST /api/cafes` / `PATCH /api/cafes/{cafe_id}`
- `GET /api/cafes/{cafe_id}/programs` / `POST /api/cafes/{cafe_id}/programs`
- `PATCH /api/cafes/{cafe_id}/programs/{program_id}`
- `GET /api/cafes/{cafe_id}/locals` / `POST /api/cafes/{cafe_id}/locals`
- `PATCH /api/cafes/{cafe_id}/locals/{local_id}`
- `POST /api/cafes/{cafe_id}/locals/{local_id}/visits`
- `GET /api/cafes/{cafe_id}/locals/{local_id}/progress`
- `POST /api/cafes/{cafe_id}/locals/{local_id}/redeem`
- `GET /api/cafes/{cafe_id}/dashboard`

### Email campaigns
- `GET /api/cafes/{cafe_id}/email-campaigns`
- `POST /api/cafes/{cafe_id}/email-campaigns`

If SMTP is not configured, campaigns are recorded as `simulated` deliveries.

### Optional SMTP variables
- `GUMM_LOCAL_SMTP_HOST`
- `GUMM_LOCAL_SMTP_PORT` (default `587`)
- `GUMM_LOCAL_SMTP_USERNAME`
- `GUMM_LOCAL_SMTP_PASSWORD`
- `GUMM_LOCAL_SMTP_USE_TLS` (default `true`)

### Media upload variables
- `GUMM_LOCAL_UPLOAD_DIR` (default `./uploads/gumm-local`)

### Business profile media limits
- Images: `jpg`, `jpeg`, `png`, `webp`, `gif` up to `10MB`
- Videos: `mp4`, `webm`, `mov` up to `25MB`

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
