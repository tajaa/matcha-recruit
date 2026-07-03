# Cappe — domain serving (MVP + later)

How published Cappe sites get served on the internet. Two layers already exist
in the app; this doc is the **edge** (DNS + TLS + nginx) that's missing.

## Topology (already true)

```
internet ──TLS──> host nginx (EC2 54.177.107.107, certbot/Let's Encrypt)
                    ├─ hey-matcha.com / www       → frontend container :8082 (SPA + /api proxy)
                    └─ *.hey-matcha.com (tenants)  → matcha-backend :8002  (renderer + /api/cappe)
```

- The **renderer** is a backend route mounted at root (`server/app/cappe/routes/render.py`).
  It routes on the `Host` header (`subdomain_from_host`), so the only requirement
  is that nginx **passes `Host` through unchanged**.
- Tenant pages are fully self-contained: inline CSS/JS, fonts from Google CDN,
  images from CloudFront. **No SPA / frontend-container involvement** — a tenant
  host proxies everything straight to the backend.
- App keeps the apex + `www` (nginx exact-match wins over the wildcard block).
  Reserved labels (`app`, `login`, `mail`, `admin`, …) never resolve to a tenant
  — see `RESERVED_SUBDOMAINS` in `routes/_shared.py`; site creation also steers
  slugs away from them.

The base domain is `CAPPE_BASE_DOMAIN` (default `hey-matcha.com`). Post-MVP, set
it to a dedicated domain and every tenant site moves with **no code change**.

---

## MVP — subdomains on the main apex (`site-x.hey-matcha.com`)

### 1. DNS (Hostinger panel)

Add **one** wildcard record:

| Type | Name | Value          | TTL |
|------|------|----------------|-----|
| A    | `*`  | 54.177.107.107 | default |

⚠️ A `*.hey-matcha.com` wildcard makes **every** undefined subdomain resolve to
the app server. Before adding it, eyeball existing records — anything already
defined (apex, `www`, mail/MX, external CNAMEs) keeps working (explicit beats
wildcard). Undefined names will now hit nginx and 404 from the renderer, which
is fine.

### 2. TLS — wildcard cert `*.hey-matcha.com`

Wildcards require a **DNS-01** challenge (Hostinger has no certbot plugin, so
this is a one-time manual TXT, renewed by hand ~every 90 days):

```bash
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107
sudo certbot certonly --manual --preferred-challenges dns \
     -d '*.hey-matcha.com' --agree-tos -m aaron@hey-matcha.com
# certbot prints a TXT record: _acme-challenge.hey-matcha.com = <value>
# add it in Hostinger DNS, wait for propagation (dig +short TXT _acme-challenge.hey-matcha.com), continue.
```

Cert lands at `/etc/letsencrypt/live/hey-matcha.com-0001/` (or similar — note
the exact path certbot prints). **Renewal reminder:** this cert does NOT
auto-renew (manual DNS-01). Put a ~75-day calendar reminder, or move to the
Caddy setup below.

### 3. nginx — wildcard server block

`/etc/nginx/conf.d/cappe.conf`:

```nginx
# Tenant Cappe sites. Wildcard server_name has LOWER precedence than the
# exact-match main-app block (hey-matcha.com / www), so the main app is
# unaffected; only other subdomains land here.
server {
    listen 443 ssl http2;
    server_name *.hey-matcha.com;

    ssl_certificate     /etc/letsencrypt/live/hey-matcha.com-0001/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hey-matcha.com-0001/privkey.pem;

    # Renderer pages + same-origin widget API both live on the backend.
    location / {
        proxy_pass http://127.0.0.1:8002;   # match the host-published backend port
        proxy_set_header Host $host;          # CRITICAL — renderer routes on Host
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }
}

server {
    listen 80;
    server_name *.hey-matcha.com;
    return 301 https://$host$request_uri;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 4. Verify

```bash
# Replace with a real published site's subdomain.
curl -sI https://avery-lane-photography.hey-matcha.com/ | head -3
curl -s  https://avery-lane-photography.hey-matcha.com/ | grep -o '<title>[^<]*</title>'
# Reserved label must NOT serve a tenant:
curl -sI https://app.hey-matcha.com/ | head -1     # 404 from renderer (or main app if you define it)
```

---

## Post-MVP — dedicated domain + custom domains (Caddy on-demand)

When moving to a dedicated domain (e.g. `*.trycappe.com`) and/or offering
customers their own domains, switch the edge to **Caddy with on-demand TLS** —
it issues a per-hostname cert on first request via HTTP-01, **no wildcard cert,
no DNS-01, no manual renewal**, for subdomains AND arbitrary custom domains.

Sketch:

- Give Cappe its own elastic IP; Caddy binds `:80/:443` there (nginx keeps the
  main app on the current IP — no :443 collision, clean separation, matches the
  "switch out later" goal).
- DNS: `*.<cappe-domain> → cappe IP`; customers point their domain's A/CNAME at
  the cappe IP.
- Caddy `on_demand_tls.ask` → a thin backend endpoint that returns 200 iff the
  host is a registered tenant (wildcard suffix) or a connected `custom_domain`.
  The check already exists: `routes/render.py:is_registered_custom_domain` +
  `subdomain_from_host`. Expose it as a tiny public route and point Caddy at it.
- Caddy reverse-proxies everything to the backend `:8002` with `Host` preserved
  (same contract as the nginx block above).

```
# Caddyfile sketch
{
    on_demand_tls {
        ask http://127.0.0.1:8002/api/cappe/internal/tls-allowed
    }
}
https:// {
    tls { on_demand }
    reverse_proxy 127.0.0.1:8002 {
        header_up Host {host}
    }
}
```

The connect-domain UI + DNS-instructions + verification flow are infra-agnostic
app code that can be built before Caddy is stood up.

---

## Prod migrations (gate this on launch)

The serving change ships no schema. But the Cappe feature set needs, in prod:

- `zzzzcappe03` — offering fulfillment (products/orders columns)
- `zzzzcappe04` — `cappe_accounts.account_type`

Both additive/safe. Pre-cutover (app still on the `:5433` container), apply to
**both** RDS and legacy: `./scripts/migrate-prod.sh` **and**
`./scripts/migrate-prod.sh --legacy`. Requires explicit approval (prod-safety
rule in root CLAUDE.md).
