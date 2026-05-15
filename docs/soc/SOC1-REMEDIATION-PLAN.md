# SOC 1 Remediation Plan — CRITICAL & HIGH Findings

**Date:** 2026-03-12
**Reference:** SOC1-ASSESSMENT.md

---

## Phase 1: Access Controls (CRITICAL)

### C1 — Replace superuser database role

**Current state:** Application connects as `matcha` which has superuser privileges.

**Steps:**
1. SSH into DB host (`3.101.83.217`), create a restricted application role:
   ```sql
   CREATE ROLE matcha_app WITH LOGIN PASSWORD '<generate-strong-password>';
   GRANT CONNECT ON DATABASE matcha TO matcha_app;
   GRANT USAGE ON SCHEMA public TO matcha_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO matcha_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO matcha_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO matcha_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO matcha_app;
   ```
2. Keep `matcha` superuser for migrations only — never used by the running app
3. Update `.env.backend` on EC2 to use `matcha_app` in `DATABASE_URL`
4. Create a separate `DATABASE_URL_MIGRATE` env var for Alembic that uses the `matcha` superuser
5. Update `server/app/database.py` to use `DATABASE_URL` (restricted)
6. Update `server/alembic/env.py` to use `DATABASE_URL_MIGRATE`
7. Test: deploy, verify app starts, verify migrations still work separately

**Risk:** If the app uses DDL at runtime (e.g., `init_db()` CREATE TABLE statements), those will fail. Audit `database.py:init_db()` to confirm it only runs during setup, not on every boot.

---

### C2 — Add Redis authentication

**Current state:** `redis-server --appendonly yes` with no password. Accessible to any container on the Docker bridge network.

**Steps:**
1. Generate a strong Redis password, add to `.env.backend` on EC2:
   ```
   REDIS_PASSWORD=<generated>
   ```
2. Update `docker-compose.yml`:
   ```yaml
   redis:
     command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
   ```
3. Update Redis URLs in `docker-compose.yml` environment blocks:
   ```yaml
   environment:
     - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
     - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
     - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/0
   ```
4. Deploy and verify backend + worker both connect successfully

---

### C3 — SSH key management policy

**Current state:** Single PEM key (`roonMT-arm.pem`) provides access to both EC2 instances with no rotation, no MFA, no documented custody.

**Steps:**
1. Document current key holders and access scope
2. Generate new key pair, distribute to authorized personnel only
3. Add new public key to both EC2 `~/.ssh/authorized_keys`
4. Remove old key after confirming new key works
5. Set calendar reminder for quarterly rotation
6. Long-term: migrate all EC2 access to AWS Session Manager (SSM) — eliminates SSH keys entirely. Both instances already have SSM agent (CI/CD uses it). Add IAM policies requiring MFA for SSM sessions.

---

### C4 — Remove hardcoded AWS Account ID

**Current state:** `update-ec2.sh:15` has `AWS_ACCOUNT_ID="010438494410"` in source control.

**Steps:**
1. Update `update-ec2.sh` to auto-detect like `build-and-push.sh` already does:
   ```bash
   AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
   ```
2. Remove the hardcoded value

---

## Phase 2: Change Management (HIGH)

### H1 — Enforce CI-only production deploys

**Current state:** `update-ec2.sh` allows anyone with the SSH key to deploy anything to production with no review or audit trail.

**Steps:**
1. Rename `update-ec2.sh` to `update-ec2-emergency.sh` to signal it's not the normal path
2. Add a prominent warning banner at the top that logs the deploy to a file or SNS
3. Document the standard deploy process: PR → review → merge to main → GitHub Actions deploys automatically
4. Document the emergency deploy process: when CI is down, use the manual script, then file an incident record
5. Long-term: remove SSH-based deploy entirely once SSM-only access is in place (C3)

### H2 — Enable GitHub branch protection

**Steps:**
1. In GitHub repo settings → Branches → Add rule for `main`:
   - Require pull request before merging (at least 1 approval)
   - Require status checks to pass (the `build-and-push` job)
   - Require branches to be up to date before merging
   - Do not allow force pushes
   - Do not allow deletions
2. Document the policy in the repo (CONTRIBUTING.md or similar)

### H3 — Verify deployment completion in CI

**Current state:** `deploy.yml` fires an SSM command and exits without checking if it succeeded.

**Steps:**
1. Update the "Deploy to EC2 via SSM" step in `deploy.yml` to capture the command ID and wait:
   ```yaml
   - name: Deploy to EC2 via SSM
     env:
       INSTANCE_ID: ${{ secrets.EC2_INSTANCE_ID }}
       AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
     run: |
       COMMAND_ID=$(aws ssm send-command \
         --instance-ids "$INSTANCE_ID" \
         --document-name "AWS-RunShellScript" \
         --parameters "commands=[...]" \
         --query 'Command.CommandId' \
         --output text)

       echo "Waiting for deployment to complete..."
       aws ssm wait command-executed \
         --instance-id "$INSTANCE_ID" \
         --command-id "$COMMAND_ID"

       STATUS=$(aws ssm get-command-invocation \
         --instance-id "$INSTANCE_ID" \
         --command-id "$COMMAND_ID" \
         --query 'Status' \
         --output text)

       if [ "$STATUS" != "Success" ]; then
         echo "::error::Deployment failed with status: $STATUS"
         exit 1
       fi
   ```
2. Add a post-deploy health check step that curls the `/health` endpoint

### H4 — Fix CI deploy to avoid downtime

**Current state:** CI pipeline runs `docker-compose down` then `docker-compose up -d`, causing a full outage window.

**Steps:**
1. Update the SSM deploy command in `deploy.yml` to match what `update-ec2.sh` already does:
   ```
   docker-compose --profile worker pull
   docker-compose --profile worker up -d --no-deps matcha-backend matcha-frontend matcha-worker
   ```
2. This pulls new images and recreates only the app containers, keeping Redis (and the network) running

---

## Phase 3: Monitoring & Logging (HIGH)

### M1 — Centralized logging with retention

**Current state:** Container logs go to local `json-file` with 30MB rotation, then are permanently lost.

**Recommended approach — CloudWatch (cheapest for this scale):**

1. Install the CloudWatch agent on the app EC2 (`54.177.107.107`):
   ```bash
   sudo yum install -y amazon-cloudwatch-agent
   ```
2. Configure it to ship Docker container logs:
   ```json
   {
     "logs": {
       "logs_collected": {
         "files": {
           "collect_list": [
             {
               "file_path": "/var/lib/docker/containers/*/*.log",
               "log_group_name": "matcha-recruit/containers",
               "log_stream_name": "{instance_id}/{filename}",
               "retention_in_days": 365
             }
           ]
         }
       }
     }
   }
   ```
3. Alternatively, switch Docker logging driver to `awslogs` in `docker-compose.yml`:
   ```yaml
   logging:
     driver: awslogs
     options:
       awslogs-group: matcha-recruit/backend
       awslogs-region: us-west-1
       awslogs-stream-prefix: matcha
   ```
4. Set log group retention to 365 days (SOC 1 audit period)
5. Also ship DB server logs from the PG host (`3.101.83.217`)

### M2 — Alerting

**Steps:**
1. Create an SNS topic `matcha-alerts` and subscribe your email/Slack
2. Add CloudWatch alarms for:
   - **Container health**: monitor the health check endpoints
   - **Disk space**: `df` metric on both EC2 instances (< 20% free)
   - **Error rate**: filter CloudWatch logs for HTTP 5xx, alert if > threshold
   - **Memory**: EC2 memory utilization
3. Add a simple uptime check (e.g., AWS Route 53 health check on the public endpoint, or free tier UptimeRobot)

### M3 — Backup failure alerting

**Current state:** Backup script logs to `~/backup.log` on the DB host. Nobody knows if it fails.

**Steps:**
1. Update `backup-postgres.sh` (the version on the DB host) to send an SNS notification on failure:
   ```bash
   on_failure() {
     aws sns publish \
       --topic-arn "arn:aws:sns:us-west-1:${AWS_ACCOUNT_ID}:matcha-alerts" \
       --subject "ALERT: Matcha DB backup failed" \
       --message "Backup failed at $(date). Check ~/backup.log on 3.101.83.217"
   }
   trap on_failure ERR
   ```
2. Add a success notification too (or at minimum, a CloudWatch custom metric) so you can alarm on "no successful backup in 12 hours"
3. Schedule a quarterly restore test: download a backup from S3, restore to a scratch database, verify row counts

### M4 — Database audit logging

**Steps:**
1. SSH into DB host, install pgaudit:
   ```bash
   sudo yum install -y pgaudit  # or compile from source if needed
   ```
2. Add to `postgresql.conf`:
   ```
   shared_preload_libraries = 'pgaudit'
   pgaudit.log = 'ddl, role'
   pgaudit.log_catalog = off
   ```
3. Restart PostgreSQL
4. Ship PG logs to CloudWatch (covered in M1)

---

## Execution Priority

| Order | Items | Effort | Impact |
|-------|-------|--------|--------|
| 1 | C2 (Redis auth), C4 (hardcoded ID) | < 1 hour | Quick wins, close critical findings |
| 2 | H2 (branch protection), H4 (fix CI deploy) | < 1 hour | GitHub settings + small YAML edit |
| 3 | H3 (verify deploy completion) | 1-2 hours | CI pipeline update |
| 4 | M3 (backup alerting) | 1-2 hours | Script update + SNS topic |
| 5 | M1 (centralized logging) | 2-4 hours | CloudWatch agent setup on both hosts |
| 6 | M2 (alerting) | 2-4 hours | CloudWatch alarms + SNS |
| 7 | C1 (restricted DB role) | 2-4 hours | Needs careful testing — app must not use DDL at runtime |
| 8 | M4 (pgaudit) | 1-2 hours | Extension install + config |
| 9 | C3 (SSH key rotation / SSM migration) | 4-8 hours | Key rotation + IAM policy updates |
| 10 | H1 (enforce CI-only deploys) | Ongoing | Process + documentation |
