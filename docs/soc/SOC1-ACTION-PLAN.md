# SOC 1 Action Plan — Solo Engineer Priority

**Date:** 2026-03-12
**Context:** Single engineer on project. Only addressing fixes that don't interfere with active development workflow.

---

## DO NOW — Safe, Low Effort

### C4 — Remove hardcoded AWS Account ID
- **File:** `update-ec2.sh:15`
- **Fix:** Replace `AWS_ACCOUNT_ID="010438494410"` with auto-detect: `AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"`
- **Effort:** 1 minute
- **Risk:** None

### N1 — Fix StrictHostKeyChecking=no
- **File:** `deploy/setup-db-instance.sh:13,16`
- **Fix:** Change `StrictHostKeyChecking=no` to `StrictHostKeyChecking=accept-new` (other scripts already do this correctly)
- **Effort:** 1 minute
- **Risk:** None

### H4 — Fix CI deploy to avoid downtime
- **File:** `deploy.yml` SSM deploy command
- **Fix:** Replace `docker-compose down` / `docker-compose up -d` with `docker-compose pull && docker-compose up -d --no-deps` (matches what `update-ec2.sh` already does)
- **Effort:** 5 minutes
- **Risk:** None — this is strictly better

### H3 — Verify deployment completion in CI
- **File:** `deploy.yml`
- **Fix:** Capture SSM command ID, `aws ssm wait command-executed`, check status, fail the pipeline if deploy failed
- **Effort:** 15 minutes
- **Risk:** None — just makes CI fail loudly on deploy failure instead of silently passing

### C2 — Add Redis authentication
- **Files:** `docker-compose.yml`, `.env.backend` on EC2
- **Fix:** Add `--requirepass` to Redis, update `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` to include password
- **Effort:** 15 minutes
- **Risk:** Low — requires one redeploy, test that backend + worker connect

### H2 — Enable GitHub branch protection
- **Where:** GitHub repo settings > Branches > `main`
- **Settings:** Require status checks to pass before merge, do not allow force pushes, do not allow deletions
- **Skip for now:** "Require PR reviews" (solo engineer — you'd review your own PRs)
- **Effort:** 2 minutes in GitHub UI
- **Risk:** None

---

## DEFER — Real disruption risk for solo engineer

### C1 — Restricted DB role
- **Why defer:** `init_db()` runs DDL on every boot (CREATE TABLE IF NOT EXISTS, ALTER TABLE, CREATE INDEX). Splitting into app role vs migration role requires auditing every SQL path, two connection strings, and careful deploy testing. High risk of breaking the running app.
- **When:** When you have a staging environment or a second engineer to test with.

### M1 — Centralized logging (CloudWatch)
- **Why defer:** Operational overhead to set up CloudWatch agent on both EC2s, costs money, ongoing maintenance. No immediate audit requirement.
- **When:** When SOC 1 Type II audit is actually scheduled.

### M2 — Alerting (CloudWatch alarms)
- **Why defer:** Depends on M1. No value without centralized logs.
- **When:** After M1.

### M3 — Backup failure alerting
- **Why defer:** Requires SNS topic creation, IAM policy updates, script changes on DB host. Useful but not urgent — backups are running and you can check manually.
- **When:** After M1/M2 infra is in place, or next time you're doing EC2 ops work.

### M4 — Database audit logging (pgaudit)
- **Why defer:** Requires extension install, Postgres config change, Postgres restart (brief downtime). Ship DB logs somewhere first (M1).
- **When:** After M1.

### C3 — SSH key rotation / SSM-only access
- **Why defer:** You're the sole key holder. Rotating keys solo has no security benefit. SSM migration is a bigger project (IAM policies, testing all access patterns).
- **When:** When onboarding a second engineer, or when deprecating SSH access entirely.

### H1 — Enforce CI-only deploys
- **Why defer:** `update-ec2.sh` is your escape hatch when CI is broken. As sole engineer, removing it creates more risk than it solves. Rename to `update-ec2-emergency.sh` as a compromise.
- **When:** When CI is fully reliable and H3 is deployed (deploy verification).

---

## Summary

| Priority | Items | Total Effort |
|----------|-------|-------------|
| Do now | C4, N1, H4, H3, C2, H2 | ~45 minutes |
| Defer | C1, M1-M4, C3, H1 | 15-25 hours |

The "do now" items close 6 findings with no workflow disruption. The deferred items are real infrastructure work best done when either a SOC audit is imminent or a second engineer is available.
