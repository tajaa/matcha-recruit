# Runbook — Encrypt matcha Production DB at Rest (sidecar migration)

**Goal:** move the **matcha** production database onto a new Postgres container whose data lives on a **KMS-encrypted EBS volume**, so matcha data is AES-256 encrypted at rest. The existing shared container keeps serving the other 8 apps and a copy of matcha becomes a test DB. Brings the "AES-256 at rest" security claim to fully true for matcha (DB + S3).

**Chosen approach:** same-host sidecar (decided 2026-05-22). Rejected: in-place root-volume swap (takes all 9 apps down + changes the host IP — see Appendix A, kept as fallback since an off-hours window exists).

**Status:** Phases A–G DONE 2026-05-23. ✅ **Migration complete** — matcha prod live on encrypted container `matcha-postgres-prod:5433`; old container `matcha-postgres:5432` is now the **development DB** (holds `matcha_test` copy). Backups repointed. See CloudFront Compliance section below for in-transit status. Write-affecting steps marked 🔴 are gated.

**Cutover record (Phase E/F, 2026-05-23):**
- Live `DATABASE_URL` source = `/home/ec2-user/matcha/.env.backend` line 2 (compose `/home/ec2-user/matcha/docker-compose.yml`). Backed up to `.env.backend.pre5433-*`. Flipped `:5432 → :5433`, `docker compose up -d --force-recreate matcha-backend matcha-worker` (force-recreate needed — env baked at create). NOTE: `/opt/matcha/.env.backend` is a stale alternate (points at unused `pg-rooney…rds` endpoint) — NOT live, do not edit.
- Backend healthy, `/health` 200, `[Matcha] Database initialized`. 4 app conns on new container, all `ssl=t`.
- Phase F: `/home/ec2-user/backup-to-s3.sh` rewritten (backed up `.pre-sidecar-*`) — prod matcha now dumped from `matcha-postgres-prod` as canonical `matcha_*`; old container's matcha labeled `matcha_test_*`; 8 other apps unchanged. Test-run verified both keys in S3.
- **Rollback (still available):** edit `.env.backend` port back to 5432, `docker compose up -d --force-recreate matcha-backend matcha-worker`. Old container untouched (holds matcha as `matcha_test`). Window to roll back cleanly = before significant new writes accumulate on the new container.

**Provisioned artifacts (B–D, 2026-05-23):**
- Encrypted volume `vol-03a6e4dfbdf769c22` (gp3 10 GB, Encrypted=true) attached `/dev/sdf` → mounted `/mnt/encdb`, PGDATA `/mnt/encdb/pgdata`.
- 1 GB swapfile added on DB host (in fstab).
- Container `matcha-postgres-prod` (pgvector/pgvector:pg15, `5433:5432`, `shared_buffers=128MB`, `ssl=on`, restart=unless-stopped).
- SG rule `sgr-0c6a879892450b61b` — 5433 from `54.177.107.107/32`.
- Roles `matcha_app`, `_rls_tester_47577f93` recreated (LOGIN, NOSUPERUSER). Dry-run restore parity: 46 companies, 240 public tables, 1917 pg_class — matches source.
- Deviation from C.1: container started plain, then `openssl` self-signed cert + `ALTER SYSTEM SET ssl=on` + restart (PG can't boot `ssl=on` without an existing cert).
**Owner:** finch. **Downtime:** matcha only, ~2–5 min during the final cutover dump/restore (82 MB). The other 8 apps stay up the whole time.

> **Why this beats the volume swap:** the DB host runs ONE container (`matcha-postgres`) holding **9 app DBs**. A root-volume swap stops all 9 and (because the host has no Elastic IP) changes the public IP → every app's `DATABASE_URL` repoints. The sidecar touches matcha only; the host IP never changes, so just matcha's `DATABASE_URL` **port** moves `5432 → 5433`.

---

## Target facts (verified 2026-05-22)

| Thing | Value |
|---|---|
| DB host instance | `i-01dfbc6406175dc87` (`t4g.micro`, arm64) @ `3.101.83.217`, AZ `us-west-1c` |
| App host instance | `i-0efcd9641849c22cd` @ `54.177.107.107` (us-west-1b) — runs `matcha-backend`, `matcha-worker`, `matcha-frontend`, `matcha-redis`, `matcha-livekit` |
| Region | `us-west-1` |
| Security group (DB) | `sg-0a210f25d08040794` — 5432 ingress restricted to `54.177.107.107/32` + `52.9.117.137/32` |
| SSH key | `roonMT-arm` (`./secrets/roonMT-arm.pem`) |
| KMS key | `alias/aws/ebs` (AWS-managed default) |
| Existing PG | container `matcha-postgres`, image `pgvector/pgvector:pg15`, named vol `matcha_postgres_data` on the **unencrypted** 8 GB root. `ssl=on`. |
| DBs in container | ⚠️ **9 apps**: `ahnimal, coronado, drooli, limited, macombe, matcha, mii, omw, otp` (+ `postgres`, `template0/1`) |
| matcha DB | **82 MB / 46 companies**. Ext: `vector 0.8.1`, `pgcrypto`, `plpgsql`. Roles: `matcha`, `matcha_app`, `_rls_tester_47577f93`. |
| Creds | `POSTGRES_USER=matcha`, `POSTGRES_PASSWORD=matcha_dev`, `POSTGRES_DB=matcha` |
| Host RAM | 916 MB total, ~434 MB free, **0 swap** → add swapfile before running 2 PG |
| Backups | `/home/ec2-user/backup-to-s3.sh` → twice-daily per-DB gzip → `s3://matcha-recruit-backups/postgres/` (SSE-AES256). Latest matcha ~11.7 MB. |

### Parameters for the new sidecar
```
export R=us-west-1 AZ=us-west-1c I=i-01dfbc6406175dc87 SG=sg-0a210f25d08040794
export NEWVOL_SIZE=10 NEWPORT=5433 NEWNAME=matcha-postgres-prod
export ENCMNT=/mnt/encdb            # mountpoint for the encrypted volume
export PGDATA_HOST=$ENCMNT/pgdata    # bind-mounted as the new container's PGDATA
```

---

## Blast radius

- **matcha only.** Final cutover stops `matcha-backend` + `matcha-worker` on the app host for ~2–5 min. The other 8 DBs and their apps are never touched.
- **No IP change, no EIP.** Same host, same `3.101.83.217`. Only matcha's `DATABASE_URL` port changes `5432 → 5433`.
- Config to update: matcha prod `.env` `DATABASE_URL` (app server, **not in repo**) + the backup script. `scripts/dev-remote.sh` / `CLAUDE.md` only if they hardcode `:5432/matcha`.

### Accepted tradeoffs (decided, not bugs)
- Two PG containers on one `t4g.micro` is permanent complexity (memory, two backup paths). Mitigated by swapfile + capped `shared_buffers`.
- "Test DB" shares the host with prod → if the host dies, both die. The test copy's value is convenience, not DR.
- The other 8 DBs stay unencrypted at rest (out of scope for the matcha claim).

---

## Phase A — Pre-flight (non-disruptive) — ✅ DONE 2026-05-22

Facts above are verified. Confirm nothing has drifted:
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 'docker ps --filter name=matcha-postgres --format "{{.Names}} {{.Image}} {{.Status}}"; free -m | head -2'
```

---

## Phase B — Provision the encrypted EBS volume (non-disruptive)

**B.1** Add swap first (no swap today; protects against OOM with 2 PG):
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  test -f /swapfile || { sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile; }
  sudo swapon /swapfile; grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
  free -m | head -2'
```

**B.2** Create the encrypted volume (same AZ as the instance):
```
ENCVOL=$(aws ec2 create-volume --region $R --availability-zone $AZ \
  --size $NEWVOL_SIZE --volume-type gp3 --encrypted --kms-key-id alias/aws/ebs \
  --tag-specifications 'ResourceType=volume,Tags=[{Key=Name,Value=matcha-prod-encrypted}]' \
  --query VolumeId --output text); echo $ENCVOL
aws ec2 wait volume-available --region $R --volume-ids $ENCVOL
aws ec2 describe-volumes --region $R --volume-ids $ENCVOL --query 'Volumes[].Encrypted'   # expect [true]
```

**B.3** Attach to the instance:
```
aws ec2 attach-volume --region $R --instance-id $I --volume-id $ENCVOL --device /dev/sdf
aws ec2 wait volume-in-use --region $R --volume-ids $ENCVOL
```

**B.4** Format + mount on the host (new disk enumerates as `/dev/nvme1n1` on Nitro):
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  lsblk    # confirm the new ~10G disk name (expect nvme1n1, empty)
  D=/dev/nvme1n1
  sudo file -s $D | grep -q ext4 || sudo mkfs.ext4 -L matchaenc $D
  sudo mkdir -p /mnt/encdb
  UUID=$(sudo blkid -s UUID -o value $D)
  grep -q "$UUID" /etc/fstab || echo "UUID=$UUID /mnt/encdb ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
  sudo mount -a && df -h /mnt/encdb
  sudo mkdir -p /mnt/encdb/pgdata && sudo chown 999:999 /mnt/encdb/pgdata'   # 999 = postgres uid in the image
```
> Gate: `df -h /mnt/encdb` shows the 10G mount AND the volume reports `Encrypted=true`. Do not proceed otherwise.

---

## Phase C — Stand up the new container (non-disruptive)

**C.1** Run the sidecar on port 5433, data on the encrypted mount, capped memory:
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  docker run -d --name matcha-postgres-prod --restart unless-stopped \
    -p 5433:5432 \
    -e POSTGRES_USER=matcha -e POSTGRES_PASSWORD=matcha_dev -e POSTGRES_DB=matcha \
    -v /mnt/encdb/pgdata:/var/lib/postgresql/data \
    pgvector/pgvector:pg15 \
    -c shared_buffers=128MB -c ssl=on \
    -c ssl_cert_file=/var/lib/postgresql/data/server.crt \
    -c ssl_key_file=/var/lib/postgresql/data/server.key
  sleep 5; docker logs --tail 20 matcha-postgres-prod'
```

**C.2** Generate a self-signed TLS cert in the new data dir + reload (matches the old container's `ssl=on` + `hostssl` posture):
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  docker exec matcha-postgres-prod bash -c "
    cd /var/lib/postgresql/data &&
    test -f server.crt || openssl req -new -x509 -days 3650 -nodes -text \
      -out server.crt -keyout server.key -subj \"/CN=matcha-prod\" &&
    chown postgres:postgres server.key server.crt && chmod 600 server.key"
  docker exec matcha-postgres-prod psql -U matcha -c "select pg_reload_conf();"
  docker exec matcha-postgres-prod psql -U matcha -tc "show ssl;"'   # expect: on
```

**C.3** Open the SG so the app host can reach 5433:
```
aws ec2 authorize-security-group-ingress --region $R --group-id $SG \
  --ip-permissions 'IpProtocol=tcp,FromPort=5433,ToPort=5433,IpRanges=[{CidrIp=54.177.107.107/32,Description="matcha app host"}]'
```

---

## Phase D — Dry-run migration (non-disruptive — validates the whole process)

This restores a copy now to prove roles/extensions/data carry over. The **authoritative** restore happens at cutover (Phase E) to capture the final delta.

**D.1** Recreate the two non-superuser roles (roles are global — NOT in a per-DB dump; `matcha` already exists via `POSTGRES_USER`):
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  docker exec matcha-postgres-prod psql -U matcha -c "
    DO \$\$ BEGIN
      CREATE ROLE matcha_app NOLOGIN;            EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;
    DO \$\$ BEGIN
      CREATE ROLE _rls_tester_47577f93 NOLOGIN;  EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;"'
```
> If `matcha_app` / `_rls_tester_47577f93` need LOGIN or specific grants, capture exact attributes from the source: `docker exec matcha-postgres pg_dumpall --roles-only | grep -iE "matcha_app|_rls_tester"` and apply verbatim.

**D.2** Dump matcha from old → restore into new (container-to-container via host):
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  TS=$(date +%Y%m%d_%H%M)
  docker exec matcha-postgres pg_dump -U matcha -Fc -d matcha -f /tmp/m_$TS.dump
  docker cp matcha-postgres:/tmp/m_$TS.dump /tmp/m_$TS.dump
  docker cp /tmp/m_$TS.dump matcha-postgres-prod:/tmp/m_$TS.dump
  # clean target, then restore
  docker exec matcha-postgres-prod psql -U matcha -d postgres -c "DROP DATABASE IF EXISTS matcha;"
  docker exec matcha-postgres-prod psql -U matcha -d postgres -c "CREATE DATABASE matcha OWNER matcha;"
  docker exec matcha-postgres-prod pg_restore -U matcha -d matcha --no-owner --role=matcha /tmp/m_$TS.dump 2>&1 | tail -20'
```

**D.3** Verify parity:
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  echo "--- extensions (expect vector, pgcrypto, plpgsql) ---"
  docker exec matcha-postgres-prod psql -U matcha -d matcha -c "\dx"
  echo "--- companies (expect 46) ---"
  docker exec matcha-postgres-prod psql -U matcha -d matcha -tc "select count(*) from companies;"
  echo "--- table count parity old vs new ---"
  docker exec matcha-postgres      psql -U matcha -d matcha -tc "select count(*) from information_schema.tables where table_schema=\"public\";"
  docker exec matcha-postgres-prod psql -U matcha -d matcha -tc "select count(*) from information_schema.tables where table_schema=\"public\";"'
```
> Gate: extensions present, 46 companies, table counts match. If yes, the migration recipe is proven.

---

## Phase E — 🔴 Cutover (matcha-only, ~2–5 min downtime; gated)

> Announce a short matcha maintenance window. The other 8 apps stay up.

**E.1** First, locate the matcha `DATABASE_URL` so the edit in E.4 is instant (recon, do before stopping anything):
```
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 '
  docker inspect matcha-backend --format "{{range .Config.Env}}{{println .}}{{end}}" | grep -i DATABASE_URL
  # note the env-file / compose path that supplies it; that file is what you edit in E.4'
```

**E.2** 🔴 Stop matcha writes (app host — other apps untouched):
```
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 'docker stop matcha-backend matcha-worker && docker ps --format "{{.Names}}" | grep matcha'
```

**E.3** 🔴 Final dump/restore (captures everything written since the dry run):
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 '
  TS=$(date +%Y%m%d_%H%M)
  docker exec matcha-postgres pg_dump -U matcha -Fc -d matcha -f /tmp/cut_$TS.dump
  docker cp matcha-postgres:/tmp/cut_$TS.dump /tmp/cut_$TS.dump
  docker cp /tmp/cut_$TS.dump matcha-postgres-prod:/tmp/cut_$TS.dump
  docker exec matcha-postgres-prod psql -U matcha -d postgres -c "DROP DATABASE IF EXISTS matcha;"
  docker exec matcha-postgres-prod psql -U matcha -d postgres -c "CREATE DATABASE matcha OWNER matcha;"
  docker exec matcha-postgres-prod pg_restore -U matcha -d matcha --no-owner --role=matcha /tmp/cut_$TS.dump 2>&1 | tail -5
  docker exec matcha-postgres-prod psql -U matcha -d matcha -tc "select count(*) from companies;"'   # sanity
```

**E.4** 🔴 Repoint matcha `DATABASE_URL` on the app server: same host `3.101.83.217`, **port `5432` → `5433`** (creds/db unchanged). Edit the env-file found in E.1.

**E.5** 🔴 Restart matcha:
```
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 'docker start matcha-backend matcha-worker && sleep 5 && docker logs --tail 30 matcha-backend'
```

**E.6** Verify cutover:
- App: log in, load a DB-backed list, create a test record → confirm it persists.
- `docker exec matcha-postgres-prod psql -U matcha -d matcha -c "show ssl;"` → on.
- Backend logs: no DB connection errors; confirm it connected to `:5433`.

**Window closes when E.6 is green.**

---

## Rollback (instant)

The old container is untouched and still holds live matcha on 5432.
```
# revert DATABASE_URL port 5433 -> 5432 in the app env-file, then:
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 'docker restart matcha-backend matcha-worker'
```
The new container/volume can be left in place or torn down later. (Note: any writes made to the new container after cutover are lost on rollback — roll back fast if E.6 fails, before users transact.)

---

## Phase F — Backups (do same day as cutover)

The cron dumps DBs on the **old** container; after cutover that matcha is the **stale test copy**. Update `/home/ec2-user/backup-to-s3.sh` so production matcha is dumped from the **new** container (port 5433 / `matcha-postgres-prod`), e.g. add a `docker exec matcha-postgres-prod pg_dump …` line and drop matcha from the old container's loop (or rename its key to `matcha_test`).
```
ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217 'cat /home/ec2-user/backup-to-s3.sh'   # read first, then edit
```
> Verify the next scheduled run lands a fresh `postgres/matcha_*.sql.gz` sourced from the new container.

---

## Phase G — Post / cleanup (after a few stable days)

- Optionally rename the old matcha to `matcha_test` to avoid confusion, or drop it to reclaim memory if the test copy isn't needed.
- `enable-ebs-encryption-by-default` so any future volume is encrypted automatically: `aws ec2 enable-ebs-encryption-by-default --region $R`.
- Memory watch: `free -m` under load; the swapfile + `shared_buffers=128MB` should hold, but confirm.
- Update `CLAUDE.md`: matcha prod DB now on container `matcha-postgres-prod`, port `5433`, encrypted volume; note the DB host is multi-app (9 DBs), not matcha-only.
- Update the security one-pager: matcha "AES-256 at rest" now true (DB + S3).

---

## Gate summary (human "go" required)

1. After Phase B — volume `Encrypted=true` + mounted → proceed.
2. After Phase C — new container up, `ssl=on`, SG rule added → proceed.
3. After Phase D — extensions + 46 companies + table parity verified → migration recipe proven.
4. Before Phase E — confirm matcha maintenance window.
5. Each 🔴 step in Phase E — eyeball previous output before next.
6. Before Phase G drops — only after several stable days.

---

## CloudFront + TLS-in-Transit Compliance (2026-05-22)

App domain: `hey-matcha.com` on `54.177.107.107` (us-west-1). TLS terminates at nginx/Certbot.

| Claim | Status | Detail |
|---|---|---|
| AES-256 at rest (DB) | ✅ | `matcha-postgres-prod` on encrypted EBS vol `vol-03a6e4dfbdf769c22`, `alias/aws/ebs` |
| AES-256 at rest (S3) | ✅ | `matcha-2` bucket SSE-AES256 confirmed |
| TLS 1.2+ in transit (app) | ✅ | `ssl_protocols TLSv1.2 TLSv1.3` via `/etc/letsencrypt/options-ssl-nginx.conf`; ECDHE/DHE-GCM ciphers; HSTS 2yr |
| TLS 1.2+ in transit (CloudFront) | ⚠️ **OPEN** | All distros `MinimumProtocolVersion=TLSv1` — locked by default `*.cloudfront.net` cert; needs custom alias + ACM cert to raise to `TLSv1.2_2021` |
| US data residency (compute) | ✅ | App + DB both `us-west-1` |
| US data residency (S3) | ✅ | `matcha-2` bucket in `us-west-1` |
| US data residency (CloudFront edges) | ✅ | Changed `E1DD3T57QD7ZP4` `PriceClass_All → PriceClass_100` (US/Canada/Europe) 2026-05-22 |

**CloudFront distro for matcha:** `E1DD3T57QD7ZP4` (`d1ri804v59kjwh.cloudfront.net`) — matcha-exclusive, origin `matcha-2.s3.us-west-1.amazonaws.com`. All public S3 access blocked; CloudFront-only access.

**Remaining open item — CloudFront TLS 1.2 minimum (no extra cost — ACM + SNI both free):**

ACM cert already requested 2026-05-22:
```
arn:aws:acm:us-east-1:010438494410:certificate/6e337bd3-7d04-481e-9ff5-54c53e0d0cb5
```

**Step 1 — Add DNS validation CNAME in Hostinger** (hey-matcha.com DNS is on Hostinger):
| Field | Value |
|---|---|
| Type | CNAME |
| Name | `_73f30af2a72cb2d37b2e851ce155e279.media` |
| Value | `_0771ca6bb725f87a6b2f86e6de5c4df7.jkddzztszm.acm-validations.aws.` |

**Step 2 — Wait for cert to validate** (2–5 min after DNS propagates):
```bash
aws acm wait certificate-validated \
  --region us-east-1 \
  --certificate-arn arn:aws:acm:us-east-1:010438494410:certificate/6e337bd3-7d04-481e-9ff5-54c53e0d0cb5
```

**Step 3 — Add alias + ACM cert + TLS 1.2 to distro** (get current config, edit, apply):
```bash
CERT_ARN=arn:aws:acm:us-east-1:010438494410:certificate/6e337bd3-7d04-481e-9ff5-54c53e0d0cb5
aws cloudfront get-distribution-config --id E1DD3T57QD7ZP4 > /tmp/cf-media.json
ETAG=$(python3 -c "import json; print(json.load(open('/tmp/cf-media.json'))['ETag'])")
python3 - <<'EOF'
import json
d = json.load(open('/tmp/cf-media.json'))
cfg = d['DistributionConfig']
cfg['Aliases'] = {'Quantity': 1, 'Items': ['media.hey-matcha.com']}
cfg['ViewerCertificate'] = {
    'ACMCertificateArn': 'arn:aws:acm:us-east-1:010438494410:certificate/6e337bd3-7d04-481e-9ff5-54c53e0d0cb5',
    'SSLSupportMethod': 'sni-only',
    'MinimumProtocolVersion': 'TLSv1.2_2021',
    'CertificateSource': 'acm'
}
json.dump(cfg, open('/tmp/cf-media-updated.json', 'w'))
EOF
aws cloudfront update-distribution \
  --id E1DD3T57QD7ZP4 \
  --if-match $ETAG \
  --distribution-config file:///tmp/cf-media-updated.json \
  --query '{Status:Distribution.Status,MinTLS:Distribution.DistributionConfig.ViewerCertificate.MinimumProtocolVersion}' \
  --output json
```

**Step 4 — Add CNAME for the domain itself in Hostinger:**
| Field | Value |
|---|---|
| Type | CNAME |
| Name | `media` |
| Value | `d1ri804v59kjwh.cloudfront.net.` |

**Step 5 — Update nginx CSP on app server** (`/etc/nginx/conf.d/matcha.conf`):
Change `https://*.cloudfront.net` → `https://media.hey-matcha.com` in both `img-src` and `frame-src`.
Then `sudo nginx -t && sudo systemctl reload nginx`.

**Step 6 — Update CLOUDFRONT_DOMAIN in prod env:**
```bash
# On 54.177.107.107:
sed -i 's|CLOUDFRONT_DOMAIN=d1ri804v59kjwh.cloudfront.net|CLOUDFRONT_DOMAIN=media.hey-matcha.com|' \
  /home/ec2-user/matcha/.env.backend
docker compose -f /home/ec2-user/matcha/docker-compose.yml up -d --force-recreate matcha-backend matcha-worker
```

After Step 6 the `⚠️ OPEN` row above flips to ✅ and the full "TLS 1.2+ in transit" claim is true across all data paths.

---

## Appendix A — Fallback: in-place root-volume swap (NOT chosen)

Viable because an off-hours window exists, but takes **all 9 apps** down and changes the host IP (no EIP today). Use only if the sidecar is abandoned.

Outline: allocate Elastic IP → `docker stop matcha-postgres` → `aws ec2 stop-instances` → snapshot root vol `vol-07fdab6019f814665` → `copy-snapshot --encrypted --kms-key-id alias/aws/ebs` → `create-volume` from encrypted snapshot (gp3, us-west-1c) → detach old root (keep as rollback) → attach encrypted vol as `/dev/xvda` → start → associate EIP → verify container auto-starts + `Encrypted=true` → repoint **all 9 apps'** `DATABASE_URL` to the new EIP. Rollback: reattach `vol-07fdab6019f814665`. Backups already exist twice-daily in `s3://matcha-recruit-backups/postgres/`.
</content>
</invoke>
