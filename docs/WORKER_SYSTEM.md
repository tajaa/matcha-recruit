# Celery Worker System

Background task processing for Matcha-Recruit using Celery and Redis.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
│                                                                  │
│  Always Running:                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ matcha-      │  │ matcha-      │  │    redis     │           │
│  │ backend      │  │ frontend     │  │              │           │
│  │ (API)        │  │ (UI)         │  │ (task queue) │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│         │                                    │                   │
│         │ queues tasks                       │                   │
│         └────────────────────────────────────┘                   │
│                                              │                   │
│  Runs on Schedule (via systemd timer):       │                   │
│  ┌──────────────────────────────────────┐    │                   │
│  │ matcha-worker                        │◄───┘                   │
│  │ - Processes queued tasks             │                        │
│  │ - Runs 5 min every 15 min            │                        │
│  │ - Frees RAM when stopped             │                        │
│  └──────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

## Tasks

The worker processes these background tasks:

| Task | Trigger | What it does |
|------|---------|--------------|
| `analyze_interview_async` | Interview ends | Analyzes transcript, extracts culture data |
| `aggregate_culture_async` | API call | Combines multiple interviews into company profile |
| `match_candidates_async` | API call | Matches candidates to company culture |
| `match_position_candidates_async` | API call | Matches candidates to specific position |

Task code location: `server/app/workers/tasks/`

## How It Works

1. **Task Created**: Backend queues a task to Redis
2. **Task Waits**: Sits in Redis queue (persisted to disk)
3. **Timer Triggers**: Every 15 min, systemd starts worker
4. **Worker Processes**: Handles all queued tasks
5. **Worker Stops**: After 5 min, worker stops to free RAM
6. **Repeat**: Timer triggers again in 15 min

## File Structure

```
matcha-recruit/
├── docker-compose.yml              # Defines all services
├── scripts/
│   └── worker-cycle.sh             # Start worker → wait → stop
├── deploy/
│   ├── matcha-worker.service       # systemd service
│   ├── matcha-worker.timer         # systemd timer (15 min)
│   └── install-worker-timer.sh     # EC2 install script
└── server/app/workers/
    ├── celery_app.py               # Celery configuration
    ├── utils.py                    # Shared utilities
    └── tasks/
        ├── interview_analysis.py   # Interview analysis task
        ├── culture_aggregation.py  # Culture aggregation task
        └── matching.py             # Candidate matching tasks
```

## Configuration

### Environment Variables

Add to `.env.backend`:

```bash
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

### Worker Schedule

Edit `deploy/matcha-worker.timer`:

```ini
[Timer]
OnBootSec=5min       # First run after boot
OnUnitActiveSec=15min # Interval between runs
```

### Worker Run Duration

Edit `deploy/matcha-worker.service`:

```ini
Environment=WORKER_RUN_TIME=300  # Seconds (5 min default)
```

## Usage

### Local Development

```bash
# Start everything except worker
docker-compose up -d

# Start worker manually when needed
docker-compose --profile worker up -d matcha-worker

# Or run worker in foreground for debugging
docker-compose --profile worker up matcha-worker

# Stop worker
docker-compose --profile worker stop matcha-worker
```

### Production (EC2)

```bash
# First time: Install the timer
sudo ./deploy/install-worker-timer.sh

# Check timer status
sudo systemctl status matcha-worker.timer

# Trigger worker immediately (don't wait for timer)
sudo systemctl start matcha-worker

# View worker logs
docker logs matcha-worker

# Check queue size
docker exec matcha-redis redis-cli LLEN celery

# Disable scheduled runs
sudo systemctl stop matcha-worker.timer
sudo systemctl disable matcha-worker.timer
```

### Always-On Mode

If you upgrade EC2 or have enough RAM, run worker 24/7:

```bash
# Add to .env or shell
export COMPOSE_PROFILES=worker

# Now worker starts with docker-compose up
docker-compose up -d

# Disable the timer (no longer needed)
sudo systemctl stop matcha-worker.timer
sudo systemctl disable matcha-worker.timer
```

## API Endpoints

### Sync (Immediate)

These run in the API process, block until complete:

```
POST /api/companies/{id}/aggregate-culture
POST /api/companies/{id}/match
POST /api/positions/{id}/match
POST /api/interviews/{id}/analyze
```

### Async (Background)

These queue to worker, return immediately:

```
POST /api/companies/{id}/aggregate-culture/async
POST /api/companies/{id}/match/async
POST /api/positions/{id}/match/async
```

Interview analysis is always async (queued when interview ends).

## Monitoring

### Check if tasks are queued

```bash
# Number of pending tasks
docker exec matcha-redis redis-cli LLEN celery

# View queue contents
docker exec matcha-redis redis-cli LRANGE celery 0 -1
```

### Check worker status

```bash
# Is worker container running?
docker ps | grep matcha-worker

# Worker logs
docker logs matcha-worker --tail 50

# Timer next trigger
systemctl status matcha-worker.timer
```

### Check task results

Tasks update the database directly. Check:
- `interviews.status` changes from `analyzing` → `completed`
- `interviews.conversation_analysis` gets populated
- `culture_profiles.profile_data` gets updated

## Troubleshooting

### Tasks stuck in queue

```bash
# Check if worker ran recently
cat /var/log/matcha-worker.log

# Trigger worker manually
sudo systemctl start matcha-worker

# Check worker logs for errors
docker logs matcha-worker
```

### Worker OOM (out of memory)

Reduce concurrency in `docker-compose.yml`:

```yaml
command: python -m celery ... --concurrency=1 --max-tasks-per-child=1
```

### Redis connection errors

```bash
# Check Redis is running
docker ps | grep redis

# Test connection
docker exec matcha-redis redis-cli ping
```

### Timer not triggering

```bash
# Check timer status
sudo systemctl status matcha-worker.timer

# Re-enable timer
sudo systemctl enable matcha-worker.timer
sudo systemctl start matcha-worker.timer

# Check system logs
journalctl -u matcha-worker.timer
journalctl -u matcha-worker.service
```

## Memory Budget (EC2 t4g.micro)

| Container | RAM | Status |
|-----------|-----|--------|
| redis | ~6 MB | Always on |
| matcha-backend | ~50 MB | Always on |
| matcha-frontend | ~2 MB | Always on |
| matcha-worker | ~85 MB | Runs 5 min/15 min |
| oceaneca-* | ~260 MB | Always on |
| **Total** | ~320 MB base | +85 MB when worker runs |

With 1GB RAM + 2GB swap, this fits comfortably.
