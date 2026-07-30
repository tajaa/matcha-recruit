# fail2ban (app EC2)

Hand-managed on the app EC2, like `deploy/nginx/`. Nothing in the deploy scripts
touches it — this directory is the source of truth, apply by hand.

Two files here: `jail.local` (jails + the whitelist) and
`filter.d/nginx-404.conf` (the 404 filter).

## A ban does not look like a ban

This has now cost two incidents, so read this first. `banaction = iptables-multiport`
REJECTs with `icmp-port-unreachable`, so a banned client gets **connection
refused, instantly** — not a timeout. Browsers render that as "Safari can't
connect to the server" and the Espresso desktop app as **"Lost connection to the
server."** Both read as a total outage while the site serves everyone else fine.

Worse, the office NATs out of a single address, so one person's stale tab bans
**the whole team at once**, which kills the "it's just me" heuristic that would
otherwise point at a local problem.

Tell a ban apart from a real outage in one command — a ban refuses only 80/443
while SSH still answers:

    nc -vz 54.177.107.107 443   # refused => banned (a real outage times out)
    nc -vz 54.177.107.107 22    # still succeeds

Then confirm and clear:

    ssh … 'sudo fail2ban-client status nginx-404'
    ssh … 'sudo fail2ban-client set nginx-404 unbanip <IP>'

## The whitelist

`jail.local` sets `ignoreip` for the office egress IP. Upstream `jail.conf` ships
that line **commented out**, so before 2026-07-30 there was no whitelist at all —
not even loopback. The office IP is residential and **will rotate**; when it does,
update `jail.local` and reload, or the entry silently protects a stranger.
`curl https://api.ipify.org` prints the current one.

## Known-inert jails

`nginx-noscript`, `nginx-badbots` and `nginx-noproxy` are `enabled = true` in
`jail.local` but their filters were never installed on this host, so fail2ban
skips them at startup. `fail2ban-client status` lists only `sshd`,
`nginx-http-auth` and `nginx-404`. They protect nothing today — install the
filters or drop the blocks, but do not assume they are running.

## Why `nginx-404` has an ignoreregex

The jail bans an IP after `maxretry = 10` 404s in `findtime = 300`s, which is the
right instinct for a scanner walking `/wp-admin`, `/.env`, `/phpmyadmin`.

But the frontend is a Vite SPA with **content-hashed** chunks
(`/assets/PtoAccrual-C3wEVKM4.js`). A blue-green deploy swaps the frontend
container and the old hashes stop existing. Any browser tab that was **open
across the deploy** is still running the old `index.html`, so as the user
navigates it lazily fetches chunk names that are now gone — dozens of 404s in
seconds, from a real user, doing nothing wrong.

On 2026-07-14 that banned the site owner out of his own site mid-deploy: 81
failures in ~2 minutes, `REJECT ... icmp-port-unreachable`, and the browser
reports "Safari can't connect to the server" — which reads as a total outage, not
as a ban. The site was serving everyone else fine.

**A 404 under `/assets/` is a stale client, never an attacker** — the paths are
unguessable hashes, so there is nothing to probe for there. Ignore them. Every
other 404 still counts, so the jail keeps doing its job.

The SPA also self-heals now (a failed dynamic import forces one reload), which
stops the burst at the source. This filter is the second layer: even if the
client-side guard fails, a legitimate user cannot be banned by it.

**The exemption requires the hash, not the directory.** Until 2026-07-30 it
matched any path under `/assets/`, which let a scanner opt out of the jail just
by prefixing its probe. The access log held exactly one `/assets/` 404 and it was
`GET /assets/priv8.php` from a webshell scanner — being ignored. Zero legitimate
chunk 404s remained, so the broad form was protecting the attacker and nobody
else. It now matches the shape Vite actually emits, `[name]-[hash][extname]`.

## Why `nginx-404` also ignores /api/ UUID paths

Second occurrence of the same class, 2026-07-30. A deleted matcha-work project
stayed in the Espresso client's cache, and every re-open fired **two** 404s —
`GET …/projects/<uuid>/bundle`, then `GET …/projects/<uuid>` — because the bundle
call's `catch` could not tell "endpoint missing on an older server" from "project
deleted", and fell through to the legacy path. Nothing evicted the project, so it
stayed re-openable. Two dead projects reached `maxretry` in seconds.

A UUID is unguessable, exactly like an asset hash, so a 404 on such a path is
always a client holding a reference to something that used to exist. Bare `/api/`
404s with no UUID (`/api/.env`, `/api/v1/users`) still count — that IS probe traffic.

The client-side cause is fixed too (`ProjectDetailViewModel+Core.swift` now
catches `APIError.httpError(404, _)` explicitly and calls
`MatchaWorkService.forgetProject`), so this filter is again the second layer.

## Verify a filter change BEFORE reloading

`fail2ban-regex` runs the candidate filter against the real log without
installing it. Do this every time — the first attempt at the tightened `/assets/`
rule silently matched nothing, because the path is followed by ` HTTP/1.1` inside
the quotes and the old rule's trailing `[^"]*` had been absorbing it:

    scp -i secrets/roonMT-arm.pem deploy/fail2ban/filter.d/nginx-404.conf \
        ec2-user@54.177.107.107:/tmp/nginx-404.conf
    ssh … 'sudo fail2ban-regex /var/log/nginx/access.log /tmp/nginx-404.conf'

Read the `Lines: N lines, X ignored, Y matched` summary and confirm X/Y moved the
way you intended, then check the printed ignored lines are all yours.

## Apply

Back up first — both files are edited in place and a bad one is only visible as
a jail that silently stops working.

    scp -i secrets/roonMT-arm.pem deploy/fail2ban/filter.d/nginx-404.conf \
        ec2-user@54.177.107.107:/tmp/nginx-404.conf
    scp -i secrets/roonMT-arm.pem deploy/fail2ban/jail.local \
        ec2-user@54.177.107.107:/tmp/jail.local
    ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 \
        'TS=$(date +%Y%m%d%H%M); \
         sudo cp /etc/fail2ban/filter.d/nginx-404.conf /etc/fail2ban/filter.d/nginx-404.conf.bak.$TS; \
         sudo cp /etc/fail2ban/jail.local /etc/fail2ban/jail.local.bak.$TS; \
         sudo cp /tmp/nginx-404.conf /etc/fail2ban/filter.d/nginx-404.conf; \
         sudo cp /tmp/jail.local /etc/fail2ban/jail.local; \
         sudo fail2ban-client reload'

A filter-only change can use `fail2ban-client reload nginx-404`, but anything in
`[DEFAULT]` (including `ignoreip`) needs the full `reload`.

Verify:

    sudo fail2ban-client status                  # expect: sshd, nginx-http-auth, nginx-404
    sudo fail2ban-client status nginx-404
    sudo fail2ban-client get nginx-404 ignoreip  # expect the office IP listed

End-to-end whitelist check — fire more than `maxretry` probe-shaped 404s from the
whitelisted network and confirm nothing bans:

    for i in $(seq 1 15); do curl -s -o /dev/null https://hey-matcha.com/f2b-test-$i.php; done
    ssh … 'sudo fail2ban-client status nginx-404 | grep Banned'

Unban by hand:

    sudo fail2ban-client set nginx-404 unbanip <IP>
