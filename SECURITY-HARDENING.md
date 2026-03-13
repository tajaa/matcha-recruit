# Security Hardening — Encryption at Rest & in Transit

**Audit Date:** 2026-03-12
**Scope:** matcha-recruit server, client, and infrastructure configuration

---

## Executive Summary

This document audits data encryption across the matcha-recruit platform and tracks remediation. The app handles sensitive data including medical credentials (DEA, NPI, license numbers), employee PII, resumes, and integration secrets. Several gaps were identified in both encryption at rest and encryption in transit.

---

## Current State

### What's Already Secure

| Component | Implementation | Location |
|-----------|---------------|----------|
| Integration secrets | Fernet (AES-128-CBC + HMAC-SHA256), `enc:v1:` prefix | `server/app/core/services/secret_crypto.py` |
| Passwords | bcrypt, 10 rounds, async-safe | `server/app/core/services/auth.py` |
| Asset delivery | CloudFront HTTPS URLs | `server/app/core/services/storage.py` |
| CORS | Whitelisted origins only | `server/app/main.py` |
| Rate limiting | nginx zones for API, auth, WebSocket | `client/nginx.conf` |
| Basic security headers | X-Frame-Options, X-Content-Type-Options, Referrer-Policy | `client/nginx.conf` |
| PII scrubbing | Regex masking before LLM calls | `server/app/core/services/pii_scrubber.py` |
| Container security | read_only, cap_drop ALL, no-new-privileges | `docker-compose.yml` (agent service) |

---

## Gaps Identified & Remediation

### Encryption in Transit

#### 1. PostgreSQL — No SSL/TLS

**Risk:** HIGH — Database is on a remote EC2 instance (3.101.83.217). All queries and results traverse the network unencrypted.

**Evidence:**
- `server/app/database.py:50-56` — `asyncpg.create_pool()` has no `ssl` parameter
- `server/app/workers/utils.py:18` — `asyncpg.connect()` has no `ssl` parameter
- No `?sslmode=require` in DATABASE_URL

**Remediation:**
- [x] Add `DATABASE_SSL` config setting (default: `disable` for local dev, `require` for production)
- [x] Pass `ssl.SSLContext` to asyncpg pool and worker connections
- [ ] Enable `ssl = on` in PostgreSQL server `postgresql.conf` (infrastructure)
- [ ] Generate/install server certificate on DB EC2 instance (infrastructure)

#### 2. Redis — No Authentication, No Encryption

**Risk:** MEDIUM — Redis on same Docker network (lower exposure), but no password means any container on the network can access cached data and Celery task queues.

**Evidence:**
- `docker-compose.yml:10` — `redis-server --appendonly yes` (no `--requirepass`)
- `docker-compose.yml:37-39` — `redis://redis:6379/0` (no password in URL)
- `server/app/core/services/redis_cache.py:13` — `aioredis.from_url()` with no auth

**Remediation:**
- [x] Add `--requirepass` to Redis server command
- [x] Update all `REDIS_URL` environment variables to include password
- [x] Update healthcheck to authenticate

#### 3. Nginx — HTTP Only, No HSTS

**Risk:** HIGH — Production frontend served over HTTP. No HTTPS listener, no HSTS header, no HTTP-to-HTTPS redirect.

**Evidence:**
- `client/nginx.conf:56` — `listen 80;` (only port)
- No `Strict-Transport-Security` header
- No `listen 443 ssl` block

**Remediation:**
- [x] Add HSTS, CSP, and Permissions-Policy headers
- [x] Add commented HTTPS server block template for when certs are provisioned
- [ ] Provision SSL certificates (Let's Encrypt / ACM) (infrastructure)
- [ ] Enable port 443 listener and HTTP-to-HTTPS redirect (infrastructure)

---

### Encryption at Rest

#### 4. S3 Uploads — No Server-Side Encryption

**Risk:** MEDIUM — Resumes, logos, offer letter PDFs, and ER case documents stored unencrypted in S3.

**Evidence:**
- `server/app/core/services/storage.py:106-111` — `put_object()` called without `ServerSideEncryption` parameter

**Remediation:**
- [x] Add `ServerSideEncryption='AES256'` to all `put_object()` calls (SSE-S3)
- [ ] Set default bucket encryption policy via AWS console (covers existing objects)

#### 5. Medical Credentials — Plaintext in Database

**Risk:** HIGH — DEA numbers, NPI numbers, license numbers, and malpractice policy numbers stored as plaintext VARCHAR in `employee_credentials` table. These are regulated identifiers.

**Evidence:**
- `server/app/database.py:2228-2259` — Table definition with plaintext columns
- `server/app/matcha/routes/employees.py:1913,2150,4648,4702` — CRUD operations without encryption

**Fields affected:** `license_number`, `npi_number`, `dea_number`, `malpractice_policy_number`

**Remediation:**
- [x] Create `credential_crypto.py` module reusing existing Fernet pattern
- [x] Add encrypt-on-write / decrypt-on-read at all 5 code paths
- [ ] Alembic migration to widen columns from VARCHAR(20/100) to VARCHAR(300) — Fernet ciphertext is ~130+ chars (**requires prod DB approval**)
- [ ] One-time backfill script to encrypt existing plaintext rows (**requires prod DB approval**)

---

### Security Headers & Middleware

#### 6. FastAPI — No Security Headers or Host Validation

**Risk:** LOW-MEDIUM — API responses lack security headers. No TrustedHostMiddleware means the backend accepts requests for any Host header.

**Evidence:**
- `server/app/main.py` — Only CORS middleware configured

**Remediation:**
- [x] Add `TrustedHostMiddleware` with allowed hosts
- [x] Add custom middleware for `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control`

#### 7. Deprecated X-XSS-Protection Header

**Risk:** LOW — `X-XSS-Protection` is deprecated and can introduce vulnerabilities in older browsers. CSP is the proper replacement.

**Evidence:**
- `client/nginx.conf:65` — `add_header X-XSS-Protection "1; mode=block" always;`

**Remediation:**
- [x] Remove `X-XSS-Protection` header
- [x] Replace with `Content-Security-Policy` header

---

## Infrastructure Prerequisites

These items cannot be done in code alone and require manual infrastructure work:

| Item | Where | Notes |
|------|-------|-------|
| Enable PostgreSQL SSL | EC2 DB server `postgresql.conf` | Set `ssl = on`, generate self-signed cert |
| Provision SSL certificates | AWS ACM or Let's Encrypt | For hey-matcha.com domain |
| Enable nginx HTTPS | EC2 app server | Uncomment 443 block, mount certs |
| S3 bucket default encryption | AWS S3 console | Encrypts existing objects retroactively |
| Widen credential columns | Production database | Alembic migration — `VARCHAR(20)` → `VARCHAR(300)` |
| Encrypt existing credential rows | Production database | One-time backfill script |

---

## Verification Checklist

- [ ] S3: Upload file → check object metadata for `ServerSideEncryption: AES256`
- [ ] PostgreSQL: Set `DATABASE_SSL=require` → server connects successfully (after infra)
- [ ] Redis: `redis-cli ping` without auth → rejected; with `-a password` → PONG
- [ ] Credentials: Upsert via API → database shows `enc:v1:...` prefix on sensitive fields
- [ ] Nginx: `curl -I` → HSTS, CSP, Permissions-Policy headers present
- [ ] FastAPI: `curl -I /health` → X-Content-Type-Options, X-Frame-Options headers present
- [ ] Tests: `cd server && python3 -m pytest tests/ -v` passes

---

## Encryption Architecture Overview

```
                    ┌─────────────────────────────────────────────┐
                    │              CLIENT (Browser)                │
                    │  Tokens in localStorage (Bearer auth)       │
                    └──────────────────┬──────────────────────────┘
                                       │
                              HTTPS (after cert provisioning)
                              HSTS enforced
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │           NGINX (Reverse Proxy)              │
                    │  TLS termination, security headers           │
                    │  CSP, HSTS, Permissions-Policy               │
                    └──────────────────┬──────────────────────────┘
                                       │
                              HTTP (Docker internal network)
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │           FastAPI (Backend)                   │
                    │  TrustedHostMiddleware                        │
                    │  Security headers middleware                  │
                    │  Fernet encrypt/decrypt for credentials       │
                    └───────┬──────────────────┬──────────────────┘
                            │                  │
                   SSL/TLS  │                  │  redis:// (Docker net)
                   (require)│                  │  --requirepass
                            │                  │
                   ┌────────▼───────┐  ┌───────▼────────┐
                   │  PostgreSQL    │  │     Redis       │
                   │  (EC2 remote)  │  │  (Docker local) │
                   │                │  │  Auth required   │
                   └────────────────┘  └────────────────┘
                                              │
                   ┌──────────────────────────▼──────────────────┐
                   │           S3 (File Storage)                  │
                   │  SSE-S3 (AES-256) on all uploads             │
                   │  CloudFront HTTPS delivery                   │
                   └──────────────────────────────────────────────┘
```

### Field-Level Encryption

| Data Type | Method | Key Source |
|-----------|--------|-----------|
| Integration secrets (OAuth tokens, API keys) | Fernet (AES-128-CBC + HMAC-SHA256) | `JWT_SECRET_KEY` via SHA256 |
| Medical credentials (DEA, NPI, license, malpractice) | Fernet (same scheme) | `JWT_SECRET_KEY` via SHA256 |
| Passwords | bcrypt (one-way hash, 10 rounds) | Random salt per password |
| S3 objects | SSE-S3 (AES-256) | AWS-managed keys |
