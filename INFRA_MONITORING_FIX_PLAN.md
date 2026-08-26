# Fix the production infra monitoring workflows (PR #277 follow-up)

## Context

PR #277 (`auto-gh-infra-checks`, merged 2026-08-25 20:20 UTC) added three ops workflows.
All three are unusable as shipped:

| Workflow | Observed | Reality |
|---|---|---|
| `availability-checks.yml` | red (run 32914746888) | 6 alerts — 5 are monitor bugs, 1 is a real production emergency |
| `post-deploy-error-regression.yml` | red at 23:48, **green at 00:30** | Working as designed; caught a genuine regression in `b7b6b9e`, cleared after `6d91c93`/`23ba2dc` |
| `operational-integrity-checks.yml` | **0 runs ever** | Schedule hasn't fired; `backup-integrity` job will fail on first run |

The monitor is currently worse than no monitor: it emits 5 false alerts, and one of its
recommendations (enable `matcha-worker.timer`) would take production's Celery worker down
every 15 minutes. The goal is a monitor whose red means something.

### Live state verified for this plan (read-only probes)

- App host `54.177.107.107`: `/` = 16G total, 7.1G free (56% used). `matcha-worker` `Up`, celery ping ok.
- DB host `13.56.253.173`: `/` = 8.0G, 3.1G free (63%); `/mnt/encdb` = 9.8G, 9.0G free (3%).
- `matcha-worker.timer` **disabled/inactive**; `matcha-worker.service` `ExecStart` →
  `/home/ec2-user/matcha/scripts/worker-cycle.sh`, **which still exists on the host** and does
  `docker-compose --profile worker up -d` → `sleep 300` → `stop matcha-worker`.
  There is no `crontab` binary and no `/etc/cron.d` on the host, so CLAUDE.md's documented
  "hourly host cron re-fires `@worker_ready`" does not exist either. Periodic Celery tasks
  currently re-dispatch **only on deploy**.
- `lego-gummfit.service`: **failed daily since ~Aug 11**. `*.gummfit.com` expires
  **2026-09-10** (16 days). Root cause in journal:
  `dns01: error presenting token (*.gummfit.com): hostinger: no subdomain because the domain and the zone are identical: dburfxi3p5e15.cloudfront.net.`
  A wildcard `* CNAME → dburfxi3p5e15.cloudfront.net` in the Hostinger zone now covers
  `_acme-challenge.gummfit.com`; lego 5.2.2 follows the CNAME and tries to write the TXT into
  `cloudfront.net`. `deploy/nginx/cappe.conf` serves `/etc/lego/certificates/gummfit.com.crt`,
  so gummfit.com breaks on Sep 10.
- App host has **no** `postgres` image (`docker image ls | grep postgres` → empty), and
  `scripts/update-ec2.sh:247 cleanup()` runs `docker image prune -a -f` on every deploy, so
  pre-pulling will not stick.
- Schema-drift job would pass: runner `matcha-opencode-mac` online; local pg_dump 15.18 /
  prod 15.15; `alembic_version` sets **identical** (13 heads, exact match).

---

## 1. `scripts/ops-health/availability.py` — stop emitting false alerts

### 1a. Disk thresholds (fixes 2 of 6 alerts)

Absolute byte floors of 8 GiB / 4 GiB are larger than these volumes can ever sustain.
Percentage thresholds are correct and stay; the byte floors become a tiny-volume backstop only.

```python
DISK_WARN_PERCENT = 80          # unchanged
DISK_CRITICAL_PERCENT = 90      # unchanged
# Absolute floors are a backstop for volumes small enough that a percentage is
# meaningless, NOT a capacity target. App root is 16G and DB root is 8G, so an
# 8 GiB "free" floor was permanently tripped at 56% used.
DISK_WARN_BYTES = 1 * 1024**3
DISK_CRITICAL_BYTES = 512 * 1024**2
```

Post-change: app 56% / 7.1G free → ok; db 63% / 3.1G free → ok; encdb 3% / 9.0G → ok.

### 1b. Worker assertions (fixes 3 of 6 alerts)

Keep `assess_worker`'s structure and the unit name `matcha-worker.timer` — §3 makes that unit
real and safe. Only the cadence tolerance changes, since the restored timer is hourly, not
15-minutely:

```python
elif timer_age > 90 * 60:
    failures.append(f"matcha-worker.timer last triggered {timer_age // 60} minutes ago")
```

Container-running, celery-ping, `timer_result`, and `timer_last` checks are already correct —
leave them.

### 1c. Disk alert body names the mount

`availability-checks.yml:116` prints `item.get('host', item.get('mount'))`, and `host` is always
present for disks, so the alert says `app` and never which filesystem. Change to:

```python
label = item.get("mount") and f"{item['host']}:{item['mount']}" or item.get("host")
print(f"- `{label}`: {item.get('reason', item.get('severity'))}")
```

---

## 2. `scripts/ops-health/backup-probe.sh` — make the restore probe runnable

Both `docker run` invocations (lines 69 and 79) use `--pull=never` against
`public.ecr.aws/docker/library/postgres:15-alpine`, which is absent and is re-evicted by every
deploy's `docker image prune -a -f`. Change **both** to `--pull=missing`.

`--pull=missing` keeps the offline/no-network-fetch behaviour when the image is cached and
pulls (~90 MB, host has 7.1G free and working AWS/network egress) only when the prune removed
it. All other hardening flags (`--network none --read-only --cap-drop ALL
--security-opt no-new-privileges`, no `--dbname`) are unchanged, so the probe still cannot
reach or restore into any database.

---

## 3. Worker scheduling — replace the dead unit, then the check means something

### 3a. `deploy/matcha-worker.service` — rewrite

The current `ExecStart` runs the retired cycle script, which **stops** the worker. Replace the
whole file:

```ini
[Unit]
Description=Recycle the Matcha Celery worker so @worker_ready re-dispatches periodic tasks
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/docker restart matcha-worker

[Install]
WantedBy=multi-user.target
```

`/usr/bin/docker` verified on host. Runs as root (systemd default), so no docker-group
dependency.

### 3b. `deploy/matcha-worker.timer` — hourly, matching CLAUDE.md's documented cadence

```ini
[Unit]
Description=Recycle the Matcha worker hourly

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

### 3c. `scripts/update-ec2.sh` — install the units on backend deploys

Add `install_worker_timer()` modelled exactly on the existing `backup_database()`
(`scripts/update-ec2.sh:118-132`) — same scp-to-`/tmp` + `sudo install` + `daemon-reload` +
`enable --now` shape, same non-fatal `log_warn` on failure so a monitoring unit can never fail a
healthy swap:

```bash
install_worker_timer() {
    # The host's stale scripts/worker-cycle.sh STOPS the worker after 300s — it
    # predates the continuous-worker design. Remove it so the unit can never
    # drift back to it, then install the recycle timer that re-fires @worker_ready.
    log_info "Installing worker recycle timer..."
    if scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
            deploy/matcha-worker.service deploy/matcha-worker.timer \
            "$EC2_USER@$EC2_HOST:/tmp/" \
        && ssh_cmd "sudo rm -f /home/ec2-user/matcha/scripts/worker-cycle.sh && sudo install -m 0644 /tmp/matcha-worker.service /etc/systemd/system/matcha-worker.service && sudo install -m 0644 /tmp/matcha-worker.timer /etc/systemd/system/matcha-worker.timer && sudo systemctl daemon-reload && sudo systemctl enable --now matcha-worker.timer"
    then
        log_success "Worker recycle timer installed"
    else
        log_warn "Could not install worker recycle timer — deploy continues"
    fi
}
```

Call it from the same place `backup_database()` is called (normal, non-`--hotfix` backend
deploys only — `--hotfix` must stay pull + swap and nothing else).

### 3d. `deploy/install-worker-timer.sh` — delete

It `chmod +x`es `scripts/worker-cycle.sh`, which no longer exists in the repo, and its job is now
`install_worker_timer()`. Removing it prevents anyone re-installing the worker-stopping unit by hand.

---

## 4. `scripts/ops-health/error-regression.py` — suppress blue/green redis churn

Every container swap tears down redis pubsub subscribers; issues #258-267 are all that noise at
deploy timestamps. Two new keys is enough to trip `alert`, so this will periodically redden a
healthy deploy.

Add above `grouped()`:

```python
# Blue/green swaps tear down every redis pubsub subscriber. The reconnect error
# is deploy mechanics, not a code regression, and two of them are enough to trip
# the alert threshold on an otherwise healthy rollout.
CHURN_TYPES = {"ConnectionError", "gaierror"}
CHURN_FRAME = re.compile(r"_subscriber_loop|redis/asyncio")
CHURN_MESSAGE = re.compile(
    r"Connection closed by server|Name or service not known|Connection reset by peer", re.I
)


def is_deploy_churn(row: dict) -> bool:
    if (row.get("exception_type") or "") not in CHURN_TYPES:
        return False
    traceback = row.get("traceback") or ""
    return bool(CHURN_FRAME.search(traceback) and CHURN_MESSAGE.search(row.get("message") or ""))
```

In `evaluate()`, filter **both** snapshots symmetrically and report the count so suppression is
never silent:

```python
def evaluate(baseline_rows, final_rows):
    suppressed = sum(1 for row in final_rows if is_deploy_churn(row))
    baseline = grouped([r for r in baseline_rows if not is_deploy_churn(r)])
    final = grouped([r for r in final_rows if not is_deploy_churn(r)])
    ...
    return {"alert": alert, "total_delta": total_delta, "suppressed_deploy_churn": suppressed,
            "changes": sorted(...)}
```

Pass/fail semantics of `post-deploy-error-regression.yml` are otherwise **unchanged** — that
workflow is correct and its 23:48 red was a true positive.

---

## 5. gummfit wildcard cert — the one real alert

### 5a. `deploy/lego-renew-gummfit.sh` — new file, versioned copy of the host script

The live script is unversioned at `/usr/local/bin/lego-renew-gummfit.sh`. Check it in verbatim
with one addition before the `lego run` call:

```bash
# The Hostinger zone's wildcard `* CNAME -> dburfxi3p5e15.cloudfront.net` (added for
# Cappe/CloudFront) also covers _acme-challenge.gummfit.com. lego follows that CNAME and
# tries to write the DNS-01 TXT into cloudfront.net, which the Hostinger provider rejects
# with "no subdomain because the domain and the zone are identical". Renewal has failed
# daily since ~2026-08-11. Disabling CNAME support writes the TXT directly into the
# gummfit.com zone, where an explicit record outranks the wildcard.
export LEGO_DISABLE_CNAME_SUPPORT=true
```

Leave the unconditional wildcard-A re-assert and its `overwrite:false` warning untouched.

### 5b. Host actions (destructive-adjacent — run explicitly, confirm before each)

```bash
scp -i secrets/roonMT-arm.pem deploy/lego-renew-gummfit.sh ec2-user@54.177.107.107:/tmp/
ssh ... 'sudo install -m 0755 /tmp/lego-renew-gummfit.sh /usr/local/bin/lego-renew-gummfit.sh'
ssh ... 'sudo systemctl start lego-gummfit.service && sudo systemctl status lego-gummfit.service --no-pager'
```

Then verify the new expiry (below). If DNS-01 still fails, the fallback is removing the explicit
`_acme-challenge` CNAME from the Hostinger zone — **not** touching the `*` wildcard, which
Cappe tenant sites depend on.

---

## 6. Docs

- `docs/ops/LOGS.md` "Known gaps" (~line 199): the worker-scheduling bullet is now resolved —
  replace with a line describing the hourly `matcha-worker.timer` recycle and that
  `install_worker_timer()` reinstalls it on every normal backend deploy.
- Root `CLAUDE.md` "Background Workers (Celery)": the line claiming "an hourly host cron
  (`docker restart matcha-worker`)" is wrong — there is no cron on the host. Correct it to the
  systemd timer.

---

## Verification

1. **Unit-level, no infra needed**
   - Capture fixtures once (the same commands the workflow runs) and re-run the assessor:
     ```bash
     ssh ... 'df -Pk / | awk ...' > /tmp/app-status.txt   # and the db equivalent
     SSH_KEY=secrets/roonMT-arm.pem ./scripts/ops-health/prod-query.sh domains > /tmp/domains.json
     python3 scripts/ops-health/availability.py --domains /tmp/domains.json \
       --app-status /tmp/app-status.txt --db-status /tmp/db-status.txt --output /tmp/av.json
     ```
     Expect exit 0 once the cert is renewed; before renewal, expect exit 1 with **only** the
     `origin.gummfit.com` TLS entry — no disk and no worker entries.
   - `error-regression.py`: feed the two snapshots from run 32912393710 and confirm the two SQL
     errors still alert while redis rows land in `suppressed_deploy_churn`.

2. **Cert**
   ```bash
   echo | openssl s_client -connect origin.gummfit.com:443 -servername origin.gummfit.com 2>/dev/null \
     | openssl x509 -noout -dates
   ```
   Expect `notAfter` ≈ 90 days out (not `Sep 10 2026`). Re-check
   `systemctl status lego-gummfit.service` is `inactive (dead)` after a success, not `failed`.

3. **Worker timer**
   ```bash
   ssh ... 'systemctl list-timers matcha-worker.timer --all; systemctl is-enabled matcha-worker.timer; docker ps --filter name=matcha-worker'
   ssh ... 'docker exec matcha-worker celery -A app.workers.celery_app inspect ping --timeout 10'
   ```
   Expect `enabled`/`active`, a `NEXT` within the hour, worker `Up`, and `pong`. Confirm
   `/home/ec2-user/matcha/scripts/worker-cycle.sh` is gone.

4. **Workflows end to end**
   ```bash
   gh workflow run availability-checks.yml            # expect success; auto-closes issue #285
   gh workflow run operational-integrity-checks.yml   # first run ever — expect both jobs green
   ```
   For operational-integrity, confirm in the step summary that `restore_list_rc` and
   `restore_scan_rc` are `0` (the `--pull=missing` fix) and that schema status is `equal`.

5. **Post-deploy monitor** — unchanged behaviour; next normal deploy should dispatch and stay
   green with `suppressed_deploy_churn` > 0 in the summary if redis churn occurred.

## Out of scope

The 14 open `autofix-nofix` issues (#250-274) are application bugs surfaced by
`silent-error-autofix.yml`, which is passing. Not part of this fix.
