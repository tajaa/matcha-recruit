# Celery Worker Deployment Options

## Current Situation

EC2 instance (t4g.micro, 1GB RAM) is running 4 containers:
- oceaneca-backend: ~377MB
- matcha-backend: ~53MB
- oceaneca-frontend: ~3MB
- matcha-frontend: ~2MB

**Available RAM: ~191MB** (plus 1.2GB swap)

New containers needed for async task processing:
- **redis**: ~128MB (message broker)
- **matcha-worker**: ~512MB (Celery worker for AI tasks)

Total additional: ~640MB - **won't fit on current instance**

---

## Option 1: Upgrade EC2 Instance (Recommended)

Upgrade from t4g.micro to t4g.small:
- RAM: 1GB → 2GB
- Cost: ~$6-12/month more
- Effort: Minimal (stop instance, change type, start)

**Pros:**
- Simple, no code changes
- Worker always available
- Room for growth

**Cons:**
- Slightly higher monthly cost

---

## Option 2: On-Demand Worker

Don't run worker persistently. Start/stop as needed.

### How it works:
1. Use sync endpoints for normal operations (they still work)
2. When batch processing needed, SSH in and start worker:
   ```bash
   cd ~/matcha
   docker-compose up -d matcha-worker
   ```
3. Stop when done:
   ```bash
   docker-compose stop matcha-worker
   ```

### Existing Sync vs Async Endpoints:

| Task | Sync Endpoint | Async Endpoint |
|------|---------------|----------------|
| Culture aggregation | `POST /api/companies/{id}/aggregate-culture` | `POST /api/companies/{id}/aggregate-culture/async` |
| Candidate matching | `POST /api/companies/{id}/match` | `POST /api/companies/{id}/match/async` |
| Position matching | `POST /api/positions/{id}/match` | `POST /api/positions/{id}/match/async` |
| Interview analysis | (automatic after interview) | Queued to worker automatically |

**Pros:**
- No additional cost
- Works with current instance

**Cons:**
- Manual intervention needed
- Interview analysis won't auto-process (stays in "analyzing" status until worker runs)
- Not ideal for production

---

## Option 3: Reduce Worker Resources

Run worker with minimal resources:
```yaml
matcha-worker:
  deploy:
    resources:
      limits:
        memory: 256M  # Down from 512M
  command: celery -A app.workers.celery_app worker --loglevel=info --concurrency=1
```

**Pros:**
- Might fit on current instance
- Always running

**Cons:**
- AI tasks may OOM (out of memory)
- Slower processing (concurrency=1)
- Risky for production

---

## Recommendation

**For production:** Option 1 (upgrade instance)
- $6-12/month is worth the reliability
- Set it and forget it

**For testing/MVP:** Option 2 (on-demand)
- Use sync endpoints for now
- Start worker manually when needed
- Upgrade later when traffic increases

---

## EC2 docker-compose.yml Update Needed

Regardless of option chosen, EC2 needs updated docker-compose.yml with redis and worker:

```bash
# Copy updated docker-compose.yml to EC2
scp -i "roonMT-arm.pem" docker-compose.yml ec2-user@ec2-13-52-75-8.us-west-1.compute.amazonaws.com:~/matcha/
```

The local `docker-compose.yml` already has redis and matcha-worker defined.
