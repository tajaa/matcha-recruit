# CloudWatch Logs shipping (app EC2)

Ships container stdout and host nginx logs off the box to CloudWatch Logs, so
logs survive the blue-green deploys that **remove the old container** (and with
it, every line it ever logged). Before this, forensics on an incident reported
an hour later were often already impossible.

| File | What it is |
|---|---|
| `logs.json` | CloudWatch **agent** config for the two host nginx log files. Applied with `append-config` so the existing metrics config (namespace `Drooli/EC2`) keeps working. |
| `logs-policy.json` | The IAM policy the EC2 instance role needs. Write-only on purpose — no `CreateLogGroup`; groups are pre-created in step 2 so a compromised instance can't invent groups. |

Container logs do **not** go through the agent. The backend/frontend use the
`awslogs` docker log driver (built in `scripts/deploy-*-bluegreen.sh`) and the
worker uses `docker-compose.logging.yml`. Both are gated on
`MATCHA_LOG_DRIVER=awslogs` in `~/matcha/.env` — see step 4.

## Why the agent doesn't collect container logs

The obvious alternative — pointing the agent at
`/var/lib/docker/containers/*/*-json.log` — keys every stream on a **container
ID**, and blue-green deploys mint a new ID on every single deploy. You get an
ever-growing pile of hex-named streams with no stable identity, and file
discovery races container removal. The `awslogs` driver instead lets us name
the stream after the container (`matcha-backend-8002` / `-8003`), so the
blue-green pair keeps two stable streams that **append** across deploys.

## Order matters

An `awslogs` credential/permission failure makes `docker run` **refuse to start
the container** — it is not a degraded-logging failure, it's a
the-app-doesn't-boot failure. So the flag in step 4 is flipped **last**, only
after steps 1–3 prove the instance can actually write. If a deploy ever fails
right after enabling it, the fix is to unset `MATCHA_LOG_DRIVER` in
`~/matcha/.env` and redeploy; the blue-green health gate keeps the old
container serving in the meantime.

---

## 1. Attach an IAM instance role (BLOCKING — nothing else works first)

As of 2026-08-03 the app EC2 has **no instance role at all** (IMDSv2
`/iam/security-credentials/` returns 404), and the CloudWatch agent currently
authenticates with a static long-lived key in `~/.aws/credentials`. The
`awslogs` docker driver resolves credentials in the **Docker daemon's**
environment, not the container's, so the static key file doesn't reach it.

Verify the current state:

```bash
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

A role name means you're set — attach the policy to it. A 404 means create and
attach one (Console: EC2 → the instance → Actions → Security → Modify IAM role;
trust policy `ec2.amazonaws.com`). Then, from a laptop with admin credentials:

```bash
aws iam put-role-policy \
  --role-name <ROLE_NAME> \
  --policy-name MatchaCloudWatchLogs \
  --policy-document file://deploy/cloudwatch/logs-policy.json
```

Once a role is attached, prefer removing `~/.aws/credentials` from the host so
the agent uses the role too — one credential path, auto-rotating, nothing
long-lived on disk. Verify the agent still publishes metrics afterward.

## 2. Pre-create the log groups + retention

Groups are created here rather than by the instance so retention is set once
and the instance policy stays write-only.

```bash
for g in /matcha/backend /matcha/frontend /matcha/worker /matcha/nginx-access /matcha/nginx-error; do
  aws logs create-log-group --log-group-name "$g" --region us-west-1 2>/dev/null || true
done
# 90d for the ones you actually investigate with; 30d for the noisy/bulky ones.
for g in /matcha/backend /matcha/worker /matcha/nginx-error; do
  aws logs put-retention-policy --log-group-name "$g" --retention-in-days 90 --region us-west-1
done
for g in /matcha/frontend /matcha/nginx-access; do
  aws logs put-retention-policy --log-group-name "$g" --retention-in-days 30 --region us-west-1
done
```

## 3. Apply the agent config (host nginx logs)

`append-config` **merges** with the running metrics config. Do not use
`fetch-config` — that replaces it and you'd lose the `Drooli/EC2` metrics.

```bash
scp -i secrets/roonMT-arm.pem deploy/cloudwatch/logs.json ec2-user@54.177.107.107:/tmp/
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 \
  "sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
     -a append-config -m ec2 -s -c file:/tmp/logs.json"

# Verify: agent running, metrics still flowing, nginx lines arriving.
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 \
  "sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status"
aws logs tail /matcha/nginx-access --since 5m --region us-west-1
```

Keep one canonical `logs.json` — `append-config` replaces a previously-appended
config with the same basename, so a second differently-named file would leave
both active.

## 4. Flip container logging on

```bash
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107
echo 'MATCHA_LOG_DRIVER=awslogs' >> ~/matcha/.env
echo 'LOG_LEVEL=INFO' >> ~/matcha/.env.backend   # if not already present
```

Then deploy normally (`./scripts/build-and-push.sh && ./scripts/update-ec2.sh --matcha`)
and verify:

```bash
aws logs tail /matcha/backend --follow --region us-west-1
aws logs tail /matcha/worker  --since 20m --region us-west-1
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 "docker logs --tail 20 \$(docker ps --format '{{.Names}}' | grep '^matcha-backend')"
```

That last one must still work: Docker ≥ 20.10 keeps a local ring buffer
("dual logging") alongside a remote driver, so `docker logs` and the deploy
scripts' failure-path `docker logs --tail 80` keep functioning. Host is on
25.0.8 — verified 2026-08-03.

`LOG_LEVEL` must stay at `INFO` or lower. Several deliberately-`WARNING` log
calls (notably the client-error reports in
`server/app/core/routes/telemetry/client_errors.py`) disappear above it, and
they sit below `ERROR` specifically so they don't double-persist into
`server_error_reports` — raising the level silently drops them entirely.

## Rollback

```bash
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 \
  "sed -i '/^MATCHA_LOG_DRIVER=/d' ~/matcha/.env"
# then redeploy — containers go back to json-file (50m x 3)
```
