# Host nginx server blocks (app EC2)

These are the **host** nginx configs that live on the app EC2
(`54.177.107.107`) at `/etc/nginx/conf.d/`. They are **hand-managed** — NOT
baked into any image and NOT applied by `build-and-push.sh` / `update-ec2.sh`.
This copy is the source of truth for disaster recovery; if the box is rebuilt,
restore from here.

| File | Serves | Upstream |
|---|---|---|
| `matcha.conf` | `hey-matcha.com` | SPA `:8082`, API `:8002`, WS, LiveKit |
| `cappe.conf` | `gummfit.com` + `*.gummfit.com` (Cappe) | apex SPA `:8082`; tenant renderer `:8002` |

> The frontend **container** nginx is separate and lives in the repo at
> `client/nginx.conf` (baked into the `matcha-frontend` image).

## Apply a change

```bash
scp -i roonMT-arm.pem deploy/nginx/cappe.conf deploy/nginx/matcha.conf ec2-user@54.177.107.107:/tmp/
ssh -i roonMT-arm.pem ec2-user@54.177.107.107
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

> Not yet hardened: the `*.gummfit.com` tenant block (`cappe.conf`) still has
> `limit_conn matcha_conn 30` on its `:8002` upstream. A published Cappe site
> bursting 30+ assets could hit the same failure — left untouched pending a
> look at tenant asset paths.
