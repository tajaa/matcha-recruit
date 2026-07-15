# fail2ban (app EC2)

Hand-managed on the app EC2, like `deploy/nginx/`. Nothing in the deploy scripts
touches it — this directory is the source of truth, apply by hand.

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

## Apply

    scp -i secrets/roonMT-arm.pem deploy/fail2ban/filter.d/nginx-404.conf \
        ec2-user@54.177.107.107:/tmp/nginx-404.conf
    ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 \
        'sudo cp /tmp/nginx-404.conf /etc/fail2ban/filter.d/nginx-404.conf \
         && sudo fail2ban-client reload nginx-404'

Verify against the real log (should report 0 matches for /assets/ 404s):

    sudo fail2ban-client status nginx-404
    sudo fail2ban-regex /var/log/nginx/access.log /etc/fail2ban/filter.d/nginx-404.conf

Unban by hand:

    sudo fail2ban-client set nginx-404 unbanip <IP>
