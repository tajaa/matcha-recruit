# Host nginx server blocks (app EC2)

These are the **host** nginx configs that live on the app EC2
(`54.177.107.107`) at `/etc/nginx/conf.d/`. They are **hand-managed** — NOT
baked into any image and NOT applied by `build-and-push.sh` / `update-ec2.sh`.
This copy is the source of truth for disaster recovery; if the box is rebuilt,
restore from here.

Public TLS terminates at CloudFront with an ACM-managed certificate for
`hey-matcha.com`, `www.hey-matcha.com`, `gummfit.com`, and `*.gummfit.com`.
The EC2 origin still needs valid certificates: Certbot manages Matcha and
lego DNS-01 manages the Gummfit wildcard. Their systemd timers are the primary
renewers; `.github/workflows/certificate-renewal.yml` invokes both daily as an
external backstop and verifies the origin files, nginx config, and public TLS.

| File | Serves | Upstream |
|---|---|---|
| `matcha.conf` | `hey-matcha.com` | `matcha_frontend` / `matcha_backend` blue-green upstreams, WS, LiveKit |
| `cappe.conf` | `gummfit.com` + `*.gummfit.com` (Cappe) | apex SPA `matcha_frontend`; tenant renderer + API `matcha_backend` |

**Never hardcode `127.0.0.1:8082/8083/8002/8003` in these files.** Blue-green
deploys alternate ports and remove the old container; the active port lives in
`/etc/nginx/upstream/matcha-{frontend,backend}-active.conf` (host-only,
rewritten by `scripts/deploy-*-bluegreen.sh`). The `matcha_frontend` /
`matcha_backend` upstream groups in `matcha.conf` include those files — every
server block (cappe included) must proxy to the group names. cappe.conf
hardcoding `:8082/:8002` is exactly how gummfit.com 502'd to the maintenance
page after the 2026-07-01 swap to 8083/8003 (fixed 2026-07-02).

> The frontend **container** nginx is separate and lives in the repo at
> `client/nginx.conf` (baked into the `matcha-frontend` image).

## Apply a change

```bash
scp -i secrets/roonMT-arm.pem deploy/nginx/cappe.conf deploy/nginx/matcha.conf ec2-user@54.177.107.107:/tmp/
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107
  TS=$(date +%Y%m%d-%H%M%S)
  cd /etc/nginx/conf.d
  sudo cp cappe.conf cappe.conf.bak-$TS && sudo cp matcha.conf matcha.conf.bak-$TS
  sudo cp /tmp/cappe.conf . && sudo cp /tmp/matcha.conf .
  sudo nginx -t && sudo nginx -s reload   # restore the .bak-$TS files if -t fails
```

## Why `/assets/` is exempt from `limit_conn` (2026-06-21)

`limit_conn matcha_conn 30` caps concurrent connections per IP. nginx counts
each **HTTP/2 stream** against it. A code-split SPA first-paint opens 30-128
concurrent streams for hashed `/assets/*` chunks — gummfit.com's lazy
`CappeRoutes` pulls ~37. The burst exceeded 30 → excess streams got `503` →
`error_page → @maintenance` served `maintenance.html` (**text/html**) for the
`.js` requests → "expected a JavaScript module… got text/html" → the SPA
crashed for **every** visitor. hey-matcha.com renders an eager landing (no
chunk burst) so it never tripped it.

Fix: a dedicated `location ^~ /assets/` with `limit_conn matcha_conn 1000`
(nginx has no `limit_conn off`; a high limit overrides the inherited cap). The
cap stays on the document + `/api/` (the real abuse surface). `@maintenance`
also returns a bare `503` (no HTML body) for `/assets/` so a deploy/restart
window can't feed HTML to a module loader either.

> Still open: the `*.gummfit.com` tenant block (`cappe.conf`) keeps
> `limit_conn matcha_conn 30` on everything the renderer serves, assets
> included. A published Cappe site that opens 30+ concurrent requests from one
> POP still loses the excess — since 2026-09-11 as a 429 with `Retry-After`,
> no longer a 503. Left as is pending a look at tenant asset paths.

## Limit rejections are 429; `error_page` stays at server level (2026-09-11)

Both files set `limit_conn_status 429` and `error_page 429 = @rate_limited` in
every HTTPS server block. Before that nothing set `limit_conn_status`, so a
tripped `limit_conn` returned 503 and landed in `@maintenance`: a visitor who
was merely rate limited got the "Server is updating" page (with a **200** on
gummfit.com, since the maintenance page is served as a file).
`@rate_limited` answers `/api/` with JSON plus `Retry-After: 30`, and anything
else with nginx's built-in 429 page. `limit_req_status 429` is host-wide in
`00-matcha-limits.conf` and repeated in each block so neither depends on it.

**Declare `error_page` in the `server` block only.** nginx gives a location
the server's `error_page` list only if the location declares none of its own,
so one local line silently drops every other handler. cappe.conf's booking
locations each carried `error_page 429 = @rate_limited`, and because of it a
backend 502 reached the booking widget as nginx's HTML page instead of
`@maintenance`'s JSON.
