# Cappe Booking Access Hardening Plan

## Architecture Choice

Use the canonical protected host for AI suggestions:

```text
https://<site-subdomain>.gummfit.com
```

Custom-domain visitors may request access, but the emailed link opens the
canonical Gummfit tenant host. The session cookie and AI endpoint work only
there. Manual booking remains available on canonical and custom domains.

Supporting AI directly on arbitrary custom domains would require per-domain
CloudFront aliases and ACM automation. That is a separate project.

## 1. Schema And Service

### Migration

Modify the currently untracked file:

`server/alembic/versions/cappeaiaccess01_booking_suggestion_access.py`

Keep revision `cappeaiaccess01`. Add these invariants:

```sql
CREATE TABLE cappe_booking_suggestion_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
    client_email VARCHAR(320) NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (client_email = lower(btrim(client_email))),
    UNIQUE (site_id, client_email)
);

CREATE TABLE cappe_booking_suggestion_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
    client_email VARCHAR(320) NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (client_email = lower(btrim(client_email))),
    UNIQUE (site_id, client_email)
);
```

Add lookup indexes:

```sql
CREATE INDEX idx_cappe_clients_site_email_lower
    ON cappe_clients (site_id, lower(email));

CREATE INDEX idx_cappe_bookings_site_email_lower
    ON cappe_bookings (site_id, lower(customer_email))
    WHERE customer_email IS NOT NULL;

CREATE INDEX idx_cappe_orders_site_paid_email_lower
    ON cappe_orders (site_id, lower(customer_email))
    WHERE customer_email IS NOT NULL
      AND status IN ('paid', 'fulfilled');

CREATE INDEX idx_cappe_booking_suggestion_links_expiry
    ON cappe_booking_suggestion_links (expires_at);

CREATE INDEX idx_cappe_booking_suggestion_sessions_expiry
    ON cappe_booking_suggestion_sessions (expires_at);
```

The unique `(site_id, client_email)` constraints bound storage and enable
atomic upserts. A new redemption replaces that client's previous session for
the site.

The downgrade must remove the three indexes added to existing tables before
dropping the two access tables.

### Access Service

Modify:

`server/app/cappe/services/booking_suggestion_access.py`

Use these public contracts:

```python
SUGGESTION_LINK_TTL = timedelta(minutes=15)
SUGGESTION_SESSION_TTL = timedelta(minutes=30)
SUGGESTION_SESSION_COOKIE = "cappe_booking_suggestion"


def hash_access_token(token: str) -> str: ...


def make_access_token() -> str: ...


async def find_existing_client(
    conn,
    *,
    site_id: UUID,
    email: str,
) -> dict[str, Any] | None: ...


async def issue_suggestion_link(
    conn,
    *,
    site_id: UUID,
    email: str,
    now: datetime,
) -> tuple[str, str | None] | None: ...


async def redeem_suggestion_link(
    conn,
    *,
    site_id: UUID,
    token: str,
    now: datetime,
) -> tuple[UUID, str, str] | None: ...


async def resolve_suggestion_session(
    conn,
    *,
    site_id: UUID,
    token: str | None,
    now: datetime,
) -> str | None: ...
```

`find_existing_client()` must use only:

```sql
cappe_clients
UNION ALL cappe_bookings
UNION ALL cappe_orders WHERE status IN ('paid', 'fulfilled')
```

Make the result deterministic:

```sql
ORDER BY priority, occurred_at DESC, source_id
LIMIT 1
```

Do not query subscribers, form submissions, message threads, reviews, or
campaigns.

`issue_suggestion_link()` must replace DELETE+INSERT with:

```sql
INSERT INTO cappe_booking_suggestion_links (...)
VALUES (...)
ON CONFLICT (site_id, client_email)
DO UPDATE SET
    token_hash = EXCLUDED.token_hash,
    expires_at = EXCLUDED.expires_at,
    used_at = NULL,
    created_at = EXCLUDED.created_at
```

`redeem_suggestion_link()` must:

1. Select the active link by hash and `site_id`.
2. Require `used_at IS NULL AND expires_at > now`.
3. Lock it with `FOR UPDATE`.
4. Set `used_at = now`.
5. Upsert the session on `(site_id, client_email)`.
6. Store only the session token hash.
7. Return the raw session token once.

All route calls should create one timezone-aware
`now = datetime.now(timezone.utc)` and pass it through.

## 2. Host And Cookie Security

### Shared Host Parsing

Modify:

`server/app/cappe/services/common.py`

Add:

```python
def normalize_host_header(value: str | None) -> str | None: ...
```

It must:

- Ignore `X-Forwarded-Host`.
- Reject userinfo, commas, whitespace, controls, `/`, `\`, `?`, and `#`.
- Accept an optional numeric port.
- Handle bracketed IPv6 safely.
- Return a lowercase hostname without a trailing dot.

Use this helper in:

- `server/app/cappe/routes/render.py:_norm_host`
- `server/app/main.py:DynamicTrustedHostMiddleware`

This removes the same unsafe `split(":", 1)` authority parsing pattern from
both locations.

### Canonical Suggestion Host

Add to `booking_suggestion_access.py`:

```python
def canonical_suggestion_host(
    site: Mapping[str, Any],
    *,
    base_domain: str | None = None,
) -> str | None: ...


def canonical_suggestion_origin(
    site: Mapping[str, Any],
    *,
    base_domain: str | None = None,
) -> str | None: ...
```

The origin must be constructed only from:

```text
site.subdomain + CAPPE_BASE_DOMAIN
```

Production always returns HTTPS. Never use `Host`, `X-Forwarded-Host`, or
`X-Forwarded-Proto` to build the emailed URL.

### Route Host Enforcement

Modify:

`server/app/cappe/routes/public/booking_suggestion_access.py`

Replace `_request_origin()` and `_secure_request()` with:

```python
def _request_host(request: Request) -> str | None: ...


def _site_host_matches(
    site: Mapping[str, Any],
    host: str | None,
    *,
    canonical_only: bool,
) -> bool: ...


def _require_site_host(
    request: Request,
    site: Mapping[str, Any],
    *,
    canonical_only: bool,
) -> None: ...
```

Required behavior:

| Route | Accepted host |
| --- | --- |
| Request access | Site canonical host or that site's verified custom domain |
| Redeem link | Canonical Gummfit tenant host only |
| Access status | Canonical returns real status; custom returns `required` |
| AI suggestions | Canonical Gummfit tenant host only |
| Magic-link landing page | Canonical Gummfit tenant host only |

For non-production local tests, explicitly accept:

```text
<subdomain>.cappe.localhost
<subdomain>.localhost
```

Do not derive these hosts from forwarded headers.

### Session Dependency

Keep this signature:

```python
async def require_booking_suggestion_session(
    slug: str,
    request: Request,
) -> str:
```

Execution order:

1. Resolve the published site by slug.
2. Require that `Host` is the canonical host for that same `site_id`.
3. Read `cappe_booking_suggestion`.
4. Resolve its hash against the same `site_id`.
5. Return the verified email or raise 403.
6. Complete before any Gemini call.

### Cookie

Set the cookie unconditionally as:

```python
response.set_cookie(
    SUGGESTION_SESSION_COOKIE,
    session_token,
    max_age=1800,
    httponly=True,
    secure=True,
    samesite="lax",
    path="/",
)
```

Do not set `Domain`. That makes it host-only.

Add `Cache-Control: no-store` to redemption and status responses.

## 3. Routes And Body Limits

### Reusable Body Limiter

Move the existing route class from `bookings.py` into:

`server/app/cappe/routes/public/_body_limit.py`

Expose:

```python
MAX_PUBLIC_JSON_BODY_BYTES = 8 * 1024


class CappePublicJsonBodyLimitRoute(APIRoute):
    ...
```

Use it for:

```python
suggestions_router = APIRouter(
    route_class=CappePublicJsonBodyLimitRoute,
)

router = APIRouter(
    route_class=CappePublicJsonBodyLimitRoute,
)
```

The second router is the booking-suggestion access router. The limiter must
continue checking both declared `Content-Length` and streamed/chunked bytes
before Pydantic parsing.

### Public Routes

Keep these paths:

```text
POST /api/cappe/public/sites/{slug}/booking-suggestions/access
POST /api/cappe/public/sites/{slug}/booking-suggestions/access/redeem
GET  /api/cappe/public/sites/{slug}/booking-suggestions/access/status
POST /api/cappe/public/sites/{slug}/booking-suggestions
GET  /__cappe/booking-suggestions/access
```

The access-request response remains generic:

```json
{"status": "sent"}
```

Never return the access URL or indicate whether the client exists.

### Manual Booking

Do not add `Depends(require_booking_suggestion_session)` to:

```text
POST /api/cappe/public/sites/{slug}/bookings
GET  /api/cappe/public/sites/{slug}/booking-types/*/slots
```

Only `POST .../booking-suggestions` receives the dependency.

## 4. Browser Runtime

### Fragment Removal

Modify:

`server/app/cappe/routes/render.py`

The landing-page runtime must remove the fragment before any network request:

```javascript
var token = window.location.hash.slice(1);
history.replaceState(null, '', window.location.pathname + window.location.search);

if (!token) {
  fail('This access link is missing its token.');
  return;
}
```

Then redeem using the in-memory token.

Return the landing page with:

```python
{
    **tenant_security_headers(),
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}
```

### Remove Polling

Modify:

`server/app/cappe/services/render/assets/booking.js`

Dispatch once after the booking UI and `[data-ai]` element exist:

```javascript
box.dispatchEvent(new CustomEvent('cappe:booking-ready'));
```

Modify:

`server/app/cappe/services/render/assets/booking_suggestion_access.js`

Replace the 25 ms polling loop with:

```javascript
function initializeAccessGate() {
  var ai = box.querySelector('[data-ai]');
  if (!ai) return false;
  // Status lookup and gating.
  return true;
}

if (!initializeAccessGate()) {
  box.addEventListener(
    'cappe:booking-ready',
    initializeAccessGate,
    {once: true}
  );
}
```

No interval, recursive timeout, or permanent observer should remain.

## 5. Email And Test Fixture

Keep:

```text
ai-client@lumiere.test
```

in:

`server/scripts/seed_cappe_spa_demo.py`

Do not add a production or development API that returns raw tokens. Do not log
raw tokens.

Automated tests should capture the access URL by monkeypatching the background
email sender before transport. Separately invoke the real core email guard with
`ai-client@lumiere.test` and assert Gmail token loading and MailerSend HTTP calls
are never reached.

For a live browser delivery test, use a developer-controlled real mailbox added
manually to local data. The reserved Lumiere address verifies eligibility and
suppression, not actual inbox delivery.

## 6. Client-IP Handling

CloudFront adds another trusted proxy hop. A global `TRUSTED_PROXY_COUNT=2` is
unsafe because custom domains still connect directly.

Modify:

`server/app/core/services/redis_cache.py`

Add secret-aware hop detection:

```python
def _trusted_proxy_count(request: Request) -> int:
    count = _TRUSTED_PROXY_COUNT
    expected = os.getenv("CAPPE_CLOUDFRONT_ORIGIN_SECRET", "")
    provided = request.headers.get("x-cappe-origin-verify", "")

    if expected and provided and hmac.compare_digest(expected, provided):
        count += 1

    return count
```

Use that count in `client_ip()`.

Configuration:

| Location | Value |
| --- | --- |
| `server/.env.example` | `CAPPE_CLOUDFRONT_ORIGIN_SECRET=` |
| Local dev | Usually unset |
| EC2 `~/matcha/.env.backend` | Random 256-bit secret |
| CloudFront origin custom header | Same secret |
| nginx origin gate | Same secret |

CloudFront must overwrite `X-Cappe-Origin-Verify` at the origin, not forward a
viewer-supplied value.

## 7. Test Matrix

### `server/tests/cappe/test_cappe_booking_suggestion_access.py`

| Test | Assertion |
| --- | --- |
| Unknown email | Returns `None`; no link write |
| Imported client | Eligible |
| Any prior booking status | Eligible |
| Paid order | Eligible |
| Fulfilled order | Eligible |
| Pending/cancelled/refunded order | Ineligible |
| Subscriber only | Ineligible |
| Form submission only | Ineligible |
| Thread only | Ineligible |
| Case normalization | `Maria@Example.com` matches |
| Tenant isolation | Same email on another site does not match |
| Hash storage | Raw link/session tokens absent from SQL arguments |
| Atomic issuance | SQL uses `ON CONFLICT (site_id, client_email)` |
| Expired link | Redemption returns `None` |
| Replay | Second redemption returns `None` |
| Wrong site | Redemption returns `None` |
| Session expiry | Resolution returns `None` |
| Session replacement | Second redemption invalidates prior session token |

### `server/tests/cappe/test_cappe_public_booking_suggestion_access.py`

| Test | Assertion |
| --- | --- |
| Unknown email | Always 202 `sent` |
| Malicious forwarded host | Emailed URL remains canonical |
| `tenant:443@attacker` header | Rejected or ignored |
| Wrong tenant host | 404/403 before issuance |
| Custom-domain request | Email points to canonical Gummfit host |
| Redeem on custom domain | Rejected |
| Redeem on wrong tenant subdomain | Rejected |
| Canonical redemption | 200 and cookie set |
| Cookie attributes | Secure, HttpOnly, Lax, Max-Age 1800, Path `/`, no Domain |
| Missing cookie | 403 |
| Expired cookie | 403 |
| Site-A cookie on site B | 403 |
| Status response | `required` or `eligible`, never cached |

Use `TestClient(base_url="https://lumiere-spa.gummfit.com")` so Secure-cookie
behavior is exercised.

### `server/tests/cappe/test_cappe_public_booking_suggestions.py`

Add actual ASGI routing tests rather than direct function calls:

| Test | Assertion |
| --- | --- |
| No session | 403 before DB slot loading or Gemini |
| Valid session | Suggestion endpoint reaches deterministic pipeline |
| Wrong-site session | 403 |
| Custom-domain host | 403 |
| Direct unit calls | Pass `verified_client_email="client@example.com"` explicitly |
| Manual booking route | Has no suggestion-session dependency |
| Manual booking without cookie | Reaches normal booking validation, not 403 |

### `server/tests/cappe/test_cappe_booking_suggestion_body_limit.py`

Parameterize declared and chunked 8,193-byte bodies across:

```text
/booking-suggestions
/booking-suggestions/access
/booking-suggestions/access/redeem
```

Every case must return 413 before its endpoint runs.

### `server/tests/cappe/test_cappe_booking_suggestion_access_email.py`

Add:

- Token appears only after `#`.
- Canonical URL ignores request forwarding headers.
- `ai-client@lumiere.test` reaches no Gmail or MailerSend transport.
- Subject and site/client names remain escaped.

### `server/tests/cappe/test_cappe_render_blocks.py`

Add:

- Manual day/time picker still rendered.
- Final `/bookings` request still rendered.
- Access form replaces only `[data-ai]`.
- `cappe:booking-ready` is emitted/listened for.
- No `setTimeout(findAi, 25)` remains.

### `server/tests/core/test_redis_cache_client_ip.py`

| Chain | Secret | Expected IP |
| --- | --- | --- |
| Direct nginx | None | Viewer |
| Spoof + direct nginx | None | Actual viewer |
| Viewer + CloudFront + nginx | Valid | Viewer |
| Spoof + viewer + CloudFront + nginx | Valid | Viewer |
| Same chain | Missing/wrong | CloudFront edge, never spoofed value |

### Manual Real-DB Test

Add:

`server/tests/cappe/test_cappe_booking_suggestion_access_realdb.py`

Guard it with an explicit environment variable such as:

```text
RUN_CAPPE_ACCESS_REALDB_TESTS=1
```

It must refuse non-local database hosts, use reserved-domain records, create no
schema, and clean up all rows. Cover simultaneous issuance and simultaneous
redemption. Do not include this file in normal automated pytest commands.

## 8. Nginx

Modify:

`deploy/nginx/cappe.conf`

Add an exact location for access and redemption in both apex and wildcard
server blocks:

```nginx
location ~ ^/api/cappe/public/sites/[^/]+/booking-suggestions/access(?:/redeem)?$ {
    limit_req zone=matcha_api burst=5 nodelay;
    client_max_body_size 8k;
    client_body_timeout 10s;
    # Preserve the existing blue/green upstream and proxy headers.
}
```

Keep the existing stricter suggestion location.

Add a CloudFront origin gate to the canonical Gummfit HTTPS server blocks. The
secret must live only on the EC2 host:

```text
/etc/nginx/snippets/cappe-cloudfront-origin-gate.conf
```

Add a secret-free template:

`deploy/nginx/cappe-cloudfront-origin-gate.conf.example`

CloudFront sends:

```text
X-Cappe-Origin-Verify: <random-secret>
```

The nginx gate rejects canonical Gummfit requests without the expected header
after DNS cutover. Custom-domain virtual hosts remain separate.

Preserve:

```nginx
proxy_set_header Host $host;
```

The backend renderer and host binding require the viewer host.

Run `nginx -t` before every reload.

## 9. CloudFront And WAF

### DNS Prerequisites

Add the ACM validation record exactly as supplied:

```text
_46f04af798bd2a046abe1c60af899754.gummfit.com
CNAME
_a458fbd9dde585dfd6425839e05b747d.jkddzztszm.acm-validations.aws
```

Create an exact origin record before changing the wildcard:

```text
origin.gummfit.com
A
54.177.107.107
```

The exact record prevents `origin.gummfit.com` from following the future
wildcard CloudFront record and creating an origin loop. `origin` is already a
reserved Cappe subdomain.

Verify whether Hostinger supports an apex `ALIAS`/`ANAME` or CNAME flattening.
If not, move authoritative DNS to Route 53. Do not place a normal CNAME at the
zone apex and do not use CloudFront edge IPs in A records.

### Distribution

Create one distribution with:

| Setting | Value |
| --- | --- |
| Aliases | `gummfit.com`, `*.gummfit.com` |
| Certificate | ACM ARN ending `c9fc7dbe-13e8-4fdb-a50a-3a4f45c6672b` |
| Origin | `origin.gummfit.com` |
| Origin protocol | HTTPS only |
| Viewer protocol | Redirect HTTP to HTTPS |
| Methods | GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE |
| Cache policy | Managed `CachingDisabled` |
| Origin request policy | All viewer headers, cookies, and query strings |
| Viewer Host | Forwarded unchanged |
| Origin custom header | `X-Cappe-Origin-Verify` |
| WAF | `cappe-public-edge` ARN |
| Compression | Enabled |
| IPv6 | Enabled |

Do not cache dynamic tenant pages or APIs initially. The origin already has
site-keyed Redis caching. Asset caching can be added later only with verified
host-independent paths or a viewer-host cache key.

### WAF Corrections

Update the existing body and rate statements to include `Method == POST`.

Keep the expensive-path regex exact:

```regex
^/api/cappe/public/sites/[^/]+/booking-suggestions$
```

Add a separate access-path regex for body protection:

```regex
^/api/cappe/public/sites/[^/]+/booking-suggestions/access(?:/redeem)?$
```

Apply the 8 KiB body rule to both POST path sets. Keep the 20 requests/5
minutes/IP rate rule targeted at the Gemini suggestion path. Backend
access-email and recipient limits remain the stricter controls for email
issuance.

## 10. Execution Order

1. Finish application, migration, tests, docs, and nginx source changes without touching a database.
2. Run `git diff --check`, focused pytest, Python compilation, and nginx configuration rendering checks.
3. Commit the migration and implementation before applying the migration anywhere.
4. With explicit approval, run `./scripts/migrate-dev.sh`.
5. Seed Lumiere and run the focused tests plus manual local checks.
6. Validate ACM.
7. Create the exact origin DNS record, CloudFront distribution, origin secret, nginx host snippet, and WAF association.
8. Test through CloudFront before DNS using `curl --connect-to`, preserving the canonical viewer host.
9. Confirm tenant A and tenant B never share cached HTML.
10. Confirm direct-origin AI requests return 403.
11. With explicit approval, run `./scripts/migrate-prod.sh`.
12. Deploy backend and nginx while keeping manual booking available.
13. Cut apex and wildcard DNS to CloudFront.
14. Verify magic redemption, cookie forwarding, authenticated suggestions, manual booking, 8 KiB rejection, WAF sampling, and direct-origin blocking.
15. Document rollback: restore the old A/wildcard records and temporarily disable the canonical-host origin gate before traffic returns directly.

Update `docs/CAPPE_AI_BOOKING_PLAN.md`, `server/app/cappe/DOMAINS.md`, and add
`docs/ops/CAPPE_EDGE.md` so the persisted session, canonical-host policy, origin
secret, cache policy, proxy count, DNS records, verification, and rollback
steps are no longer tribal knowledge.
