# Matcha-Recruit AWS Deployment Guide

## Architecture Overview

Matcha-recruit runs on a shared EC2 instance alongside Drooli (Oceaneca), for a total of **4 Docker containers**:

| Container | Port | Memory | Purpose |
|-----------|------|--------|---------|
| `oceaneca-backend` | 8001 | 384MB | Drooli FastAPI backend |
| `oceaneca-frontend` | 8080 | 64MB | Drooli React frontend |
| `matcha-backend` | 8002 | 384MB | Matcha FastAPI backend |
| `matcha-frontend` | 8082 | 64MB | Matcha React frontend |

**Total memory usage**: ~900MB on a 2GB t4g instance (ARM64 Graviton)

---

## What's Been Done

### 1. Docker Configuration (Complete)
- `server/Dockerfile` - Python 3.12 multi-stage build
- `client/Dockerfile` - Node 20 build + Nginx runtime
- `client/nginx.conf` - WebSocket proxy, security headers, gzip
- `client/docker-entrypoint.sh` - Runtime API/WS URL injection
- `docker-compose.yml` - Service orchestration with memory limits
- `.dockerignore` - Excludes node_modules, venv, etc.

### 2. Build & Deploy Scripts (Complete)
- `build-and-push.sh` - Builds ARM64 images, pushes to ECR
- `scripts/setup-ecr.sh` - Creates ECR repositories (one-time)
- `.github/workflows/deploy.yml` - CI/CD pipeline

### 3. EC2 Setup (Complete)
- Created `/opt/matcha/` directory
- Copied `docker-compose.yml`
- Created `.env.backend` with:
  - Database URL (with SSL)
  - JWT secret (auto-generated)
  - AWS credentials
  - API/WS URLs for frontend

---

## Next Steps

### 1. Create the Database
Through your RDS tunnel, run:
```sql
CREATE DATABASE matcha;
```

### 2. Add Gemini API Key
SSH into EC2 and edit the environment file:
```bash
ssh -i "roonMT-arm.pem" ec2-user@54.177.107.107
nano /opt/matcha/.env.backend
```
Replace `REPLACE_WITH_YOUR_GEMINI_API_KEY` with your actual Gemini API key.

### 3. Create ECR Repositories
Run locally (one-time):
```bash
./scripts/setup-ecr.sh
```

This creates:
- `matcha-backend` ECR repo
- `matcha-frontend` ECR repo

### 4. Add GitHub Secrets
Go to GitHub repo → Settings → Secrets → Actions, add:

| Secret | Value |
|--------|-------|
| `AWS_ACCOUNT_ID` | `010438494410` |
| `AWS_ROLE_ARN` | Same as Drooli (or create new) |
| `EC2_INSTANCE_ID` | Same as Drooli |

### 5. Deploy
Push to `main` branch to trigger GitHub Actions, or manually:
```bash
./build-and-push.sh --deploy
```

---

## EC2 Directory Structure

```
/opt/
├── oceaneca/           # Drooli
│   ├── docker-compose.yml
│   └── .env.backend
└── matcha/             # Matcha-Recruit
    ├── docker-compose.yml
    └── .env.backend
```

---

## Useful Commands

### Check all running containers
```bash
docker ps
```

### View logs
```bash
# Matcha
docker logs matcha-backend -f
docker logs matcha-frontend -f

# Drooli
docker logs oceaneca-backend -f
docker logs oceaneca-frontend -f
```

### Restart services
```bash
cd /opt/matcha && docker-compose down && docker-compose up -d
cd /opt/oceaneca && docker-compose down && docker-compose up -d
```

### Check memory usage
```bash
docker stats --no-stream
```

### Manual deployment
```bash
cd /opt/matcha
aws ecr get-login-password --region us-west-1 | docker login --username AWS --password-stdin 010438494410.dkr.ecr.us-west-1.amazonaws.com
docker-compose pull
docker-compose down
docker-compose up -d
docker system prune -f
```

---

## URLs

| Environment | Backend | Frontend |
|-------------|---------|----------|
| Production | `http://54.177.107.107:8002` | `http://54.177.107.107:8082` |
| Local Dev | `http://localhost:8000` | `http://localhost:5173` |

---

## Troubleshooting

### Container won't start
```bash
docker logs matcha-backend 2>&1 | tail -50
```

### Database connection issues
Verify SSL is in the connection string:
```
DATABASE_URL=postgresql://...?sslmode=require
```

### Memory issues
Check if containers are being OOM killed:
```bash
dmesg | grep -i "out of memory"
docker stats --no-stream
```

### Health check failing
```bash
curl http://localhost:8002/health
curl http://localhost:8082/health
```
