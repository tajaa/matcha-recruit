# Shared EC2 Instance Deployment Guide

This document explains how **matcha-recruit** and **drooli** (oceaneca) share the same EC2 instance, and critical information to prevent deployments from interfering with each other.

## EC2 Instance Access

```bash
ssh -i "roonMT-arm.pem" ec2-user@ec2-13-52-75-8.us-west-1.compute.amazonaws.com
```

**Instance Details:**
- **Region:** us-west-1
- **Architecture:** ARM64 (AWS Graviton t4g)
- **Memory:** ~2GB total
- **OS:** Amazon Linux 2

## Application Layout on EC2

```
/home/ec2-user/
├── matcha/              # matcha-recruit deployment
│   ├── docker-compose.yml
│   └── .env
├── drooli/              # drooli/oceaneca deployment
│   ├── docker-compose.yml
│   ├── certs/
│   └── .env.backend
└── roonMT-arm.pem       # SSH key (if stored on instance)
```

## Port Allocation

| Service | Matcha-Recruit | Drooli/Oceaneca |
|---------|----------------|-----------------|
| **Backend** | 8002 | 8001 |
| **Frontend** | 8082 | 8080 |
| **Worker** | N/A (background) | N/A (background) |

**Shared Services:**
| Service | Port | Used By |
|---------|------|---------|
| **PostgreSQL** | 5432 | Both (separate databases) |
| **Redis** | 6379 | Both (separate key prefixes) |

## Container Names

Each app uses prefixed container names to avoid conflicts:

**Matcha-Recruit:**
- `matcha-backend`
- `matcha-frontend`
- `matcha-worker`

**Drooli/Oceaneca:**
- `oceaneca-backend`
- `oceaneca-frontend`
- `oceaneca-worker`

**Shared:**
- `redis` (or `oceaneca-redis`)
- `postgres` (or `oceaneca-postgres`)

## Critical: Deployment Isolation Rules

### DO NOT do these things:

1. **Never run `docker-compose down` without specifying the correct directory**
   - This could stop the wrong application's containers

2. **Never run `docker system prune -a` carelessly**
   - This removes ALL unused images and could affect the other app

3. **Never modify shared PostgreSQL or Redis containers from one app's deployment script**
   - Both apps depend on these services

4. **Never change ports in docker-compose.yml without checking for conflicts**

### SAFE deployment practices:

```bash
# Matcha-Recruit - SAFE update
cd ~/matcha
docker-compose pull
docker-compose up -d --no-deps matcha-backend matcha-frontend

# Drooli - SAFE update
cd ~/drooli
docker-compose pull
docker-compose up -d --no-deps oceaneca-backend oceaneca-frontend
```

The `--no-deps` flag ensures we don't restart shared dependencies (postgres, redis).

## Memory Budget

The 2GB instance has limited memory. Both apps must stay within budget:

| Container | Memory Limit | Notes |
|-----------|--------------|-------|
| postgres | ~200MB | Shared - DO NOT restart |
| redis | ~128MB | Shared - DO NOT restart |
| matcha-backend | 384MB | 2 Uvicorn workers |
| matcha-frontend | 64MB | Nginx static serving |
| oceaneca-backend | ~400MB | 4 Uvicorn workers |
| oceaneca-frontend | 64MB | Nginx static serving |
| workers | 256MB each | Run on-demand via systemd timers |

**Total:** ~1.5GB active, leaving buffer for workers and system

## Update Scripts

### Matcha-Recruit

From local machine:
```bash
cd /path/to/matcha-recruit
./update-ec2.sh --matcha      # Update only matcha
./update-ec2.sh --status      # Check all container status
```

### Drooli

From local machine:
```bash
cd /path/to/drooli
./update-ec2.sh --oceaneca    # Update only drooli
./update-ec2.sh --status      # Check all container status
```

### Update Both (carefully)

```bash
./update-ec2.sh --all         # Updates both apps
```

## Shared Database (PostgreSQL)

Both apps use the same PostgreSQL container but **different databases**:

- Matcha uses: `matcha` database (or configured via DATABASE_URL)
- Drooli uses: `oceaneca` database (or configured via DATABASE_URL)

**Never drop or recreate the postgres container** - it contains data for both apps.

## Shared Redis

Both apps connect to the same Redis instance on port 6379.

- Apps should use different key prefixes to avoid collisions
- Matcha: Uses Redis for Celery task queue
- Drooli: Uses Redis for Celery task queue and caching

## Systemd Timers (Background Workers)

Both apps have systemd timers for background workers:

```bash
# Check timer status on EC2
systemctl list-timers --all | grep -E "(matcha|drooli)"

# Matcha worker timer
sudo systemctl status matcha-worker.timer

# Drooli worker timer
sudo systemctl status drooli-worker.timer
```

Workers run every 15 minutes, process tasks for ~5 minutes, then stop to free memory.

## Troubleshooting

### Check all containers
```bash
ssh -i "roonMT-arm.pem" ec2-user@ec2-13-52-75-8.us-west-1.compute.amazonaws.com
docker ps -a
```

### Check memory usage
```bash
docker stats --no-stream
free -h
```

### View logs for specific app
```bash
# Matcha
docker logs matcha-backend --tail 100 -f

# Drooli
docker logs oceaneca-backend --tail 100 -f
```

### If shared services are down
```bash
# Check if postgres/redis are running
docker ps | grep -E "(postgres|redis)"

# If down, bring up from drooli (which owns them)
cd ~/drooli
docker-compose up -d postgres redis
```

## Repository Links

- **matcha-recruit:** This repository
- **drooli:** `/Users/finch/Documents/github/drooli`

## Quick Reference

| What | Matcha-Recruit | Drooli |
|------|----------------|--------|
| EC2 Directory | `~/matcha` | `~/drooli` |
| Backend Port | 8002 | 8001 |
| Frontend Port | 8082 | 8080 |
| Backend Container | `matcha-backend` | `oceaneca-backend` |
| Frontend Container | `matcha-frontend` | `oceaneca-frontend` |
| Worker Container | `matcha-worker` | `oceaneca-worker` |
| Local Repo | `/github/matcha-recruit` | `/github/drooli` |

---

**Remember:** These apps share infrastructure. A careless deployment in one can break the other. Always use the safe update commands and never touch shared services (postgres, redis) unless absolutely necessary.
