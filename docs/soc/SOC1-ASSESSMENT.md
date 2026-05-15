# SOC 1 Compliance Assessment — Matcha Recruit

**Date:** 2026-03-12
**Scope:** Infrastructure, deployment, access controls, monitoring, application security

---

## Infrastructure Summary

| Component | Host | Notes |
|-----------|------|-------|
| App containers (backend, frontend, worker, agent) | EC2 `54.177.107.107` | Docker Compose |
| PostgreSQL | EC2 `3.101.83.217` | Runs directly on host (not Docker) |
| Container registry | AWS ECR (us-west-1) | |
| Backups | S3 `matcha-recruit-backups` | Every 6 hours via cron |
| CI/CD | GitHub Actions → SSM | OIDC auth, no static creds |

---

## Controls In Place

1. **OIDC for CI/CD** — GitHub Actions uses `role-to-assume`, no static AWS credentials in CI
2. **SSM for deployment** — CI/CD deploys via SSM, not SSH, creating an audit trail
3. **Container hardening** — Agent container has `cap_drop: ALL`, `read_only: true`, `no-new-privileges`
4. **Localhost-only bindings** — Backend (`127.0.0.1:8002`) and frontend (`127.0.0.1:8082`) not exposed to the internet directly
5. **Pre-deploy DB backups** — Both the CI pipeline and manual `update-ec2.sh` run backups before deploying
6. **S3 backup automation** — Cron every 6 hours, IAM role scoped to the specific S3 bucket
7. **Git SHA image tagging** — Every build is tagged with the commit hash for traceability
8. **Log rotation** — All containers use `json-file` with `max-size: 10m, max-file: 3`
9. **Health checks** — Every container has health checks configured
10. **Resource limits** — Memory caps on all containers
11. **Credentials mounted read-only** — `./credentials:/app/credentials:ro`

---

## Findings

### CRITICAL — Access Controls (CC6)

| # | Finding | Evidence | Remediation |
|---|---------|----------|-------------|
| **C1** | **Database user is superuser** | CLAUDE.md: "DB user: matcha (currently superuser)" | Create a limited-privilege application role. The app should not have `CREATE ROLE`, `DROP TABLE`, etc. |
| **C2** | **Redis has no authentication** | `docker-compose.yml`: `redis-server --appendonly yes` — no `--requirepass` | Add `--requirepass <token>` and update `REDIS_URL` to include the password |
| **C3** | **SSH key management** | `roonMT-arm.pem` used for direct root-equivalent access to both EC2s. No documented rotation, no passphrase requirement, no MFA | Rotate keys periodically. Consider AWS Session Manager for all access (eliminating SSH keys). Document key custody. |
| **C4** | **AWS Account ID hardcoded in source** | `update-ec2.sh:15` — `AWS_ACCOUNT_ID="010438494410"` | Move to environment variable or AWS CLI auto-detection (like `build-and-push.sh` already does) |

### HIGH — Change Management (CC8)

| # | Finding | Evidence | Remediation |
|---|---------|----------|-------------|
| **H1** | **Manual deploy path bypasses CI/CD** | `update-ec2.sh` allows SSH-based deploys with no PR, no review, no audit trail | Require all production deploys through the GitHub Actions pipeline. Document exception process. |
| **H2** | **No branch protection documented** | Deploy triggers on `push: main` but no evidence of required PR reviews, status checks, or signed commits | Enable GitHub branch protection: require PR reviews, require CI pass before merge |
| **H3** | **Deploy doesn't verify completion** | `deploy.yml:109-120` fires SSM command but doesn't wait for or check result | Add `aws ssm wait command-executed` + status check (like the backup step already does) |
| **H4** | **Deployment causes downtime** | CI pipeline uses `docker-compose down` then `up -d` — no rolling update | Use `docker-compose up -d --no-deps` (which `update-ec2.sh` already does correctly; the CI pipeline doesn't) |

### HIGH — Monitoring & Logging (CC7/CC9)

| # | Finding | Evidence | Remediation |
|---|---------|----------|-------------|
| **M1** | **No centralized logging** | Logs go to local `json-file` driver with 30MB rotation — then lost | Ship logs to CloudWatch, Datadog, or similar. SOC 1 auditors expect log retention for audit period (typically 12 months). |
| **M2** | **No alerting** | No CloudWatch alarms, no PagerDuty/OpsGenie, no health check alerting | Set up alarms for: container health failures, high error rates, backup failures, disk space |
| **M3** | **Backup failure is silent** | `backup-postgres.sh` logs to `~/backup.log` — nobody is alerted if it fails | Add SNS notification on backup failure. Verify backups with periodic restore tests. |
| **M4** | **No database audit logging** | No evidence of `pgaudit` or query logging for sensitive operations | Enable `pgaudit` for DDL and privileged operations at minimum |

### MEDIUM — Availability & Resilience (A1)

| # | Finding | Evidence | Remediation |
|---|---------|----------|-------------|
| **A1** | **Single point of failure — app server** | One EC2 instance for all app containers | Document accepted risk, or add a second instance behind ALB |
| **A2** | **Single point of failure — database** | One EC2 Postgres, no replication | At minimum: document RPO/RTO. Better: add streaming replication or move to RDS |
| **A3** | **No documented disaster recovery plan** | No RTO/RPO targets, no documented restore procedures | Write and test a DR runbook. Perform periodic restore from S3 backups. |

### MEDIUM — Network & Encryption

| # | Finding | Evidence | Remediation |
|---|---------|----------|-------------|
| **N1** | **`StrictHostKeyChecking=no` in setup script** | `deploy/setup-db-instance.sh:13,16` — silently accepts any host key (MITM risk) | Change to `accept-new` (which the other scripts already use), or pin known host keys |
| **N2** | **Database connection encryption unclear** | `DATABASE_URL` — no evidence of `sslmode=require` | Ensure all DB connections use TLS. Add `?sslmode=require` to connection string. |
| **N3** | **No WAF or rate limiting documented** | Backend exposed via reverse proxy (presumably nginx) but no mention of rate limiting | Add rate limiting at proxy layer. Consider AWS WAF if using ALB. |

### LOW — Code-Level

| # | Finding | Evidence | Remediation |
|---|---------|----------|-------------|
| **L1** | **health_clearances crash** | `admin.py:6097` — `dict()` called on JSON string causes ValueError | Use `json.loads()` with type check |
| **L2** | **Same pattern in employees.py** | `employees.py:4364` — identical `dict()` on JSON string | Same fix |

---

## SOC 1 Readiness Summary

| Category | Status | Priority Actions |
|----------|--------|-----------------|
| **Logical Access Controls** | Needs work | Fix superuser DB role (C1), add Redis auth (C2), key rotation policy (C3) |
| **Change Management** | Partial | Enforce CI-only deploys (H1), branch protection (H2) |
| **Monitoring** | Major gap | Centralized logging (M1), alerting (M2), backup monitoring (M3) |
| **Availability** | Documented risk | DR plan (A3), RPO/RTO targets |
| **Encryption** | Verify | DB TLS (N2) |

The biggest blockers for a SOC 1 Type II audit are **M1** (no centralized logging with retention) and **C1** (superuser database access). Auditors will ask for evidence of who accessed what and when — right now logs rotate off after ~30MB and there's no database audit trail.

---

## Quick Wins

- **C2** — Add Redis password (config change)
- **C4** — Remove hardcoded AWS Account ID from `update-ec2.sh`
- **N1** — Fix `StrictHostKeyChecking=no` in `setup-db-instance.sh`
- **L1/L2** — Fix `health_clearances` JSON parsing crash
- **H4** — Fix CI deploy to use `up -d --no-deps` instead of `down`/`up`
