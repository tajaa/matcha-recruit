#!/bin/bash
# Renew the gummfit.com wildcard cert (lego, DNS-01 via Hostinger) and reload
# nginx on success.
#
# There used to be an unconditional daily "* A -> 54.177.107.107" self-heal
# here (added 2026-06-12 after a Hostinger zone update was observed to drop
# that record during the ACME TXT dance). Removed 2026-08-27: the zone's `*`
# name is now a deliberate CNAME to CloudFront for Cappe tenant subdomains
# (`* CNAME -> dburfxi3p5e15.cloudfront.net`), so an A record can never
# coexist there — every run of that self-heal 422'd
# ("RRset *.gummfit.com IN CNAME must not be used with any other type on the
# same name"). It was silently swallowed for weeks behind a dead
# HOSTINGER_API_TOKEN; once the token was fixed the 422 surfaced and made
# clear the self-heal itself is now permanently obsolete, not just broken.
# gummfit.com's own TLS is served via the standalone `origin` A record
# (origin.gummfit.com -> 54.177.107.107), which this script never touches.
set -uo pipefail
if [ ! -r /etc/lego/hostinger.env ]; then
  echo "[$(date)] /etc/lego/hostinger.env missing or unreadable — aborting" >&2
  exit 1
fi
set -a; source /etc/lego/hostinger.env; set +a
: "${HOSTINGER_API_TOKEN:?HOSTINGER_API_TOKEN not set by hostinger.env}"
export LEGO_PATH=/etc/lego
# The Hostinger zone's wildcard `* CNAME -> dburfxi3p5e15.cloudfront.net` (added for
# Cappe/CloudFront) also covers _acme-challenge.gummfit.com. lego follows that CNAME and
# tries to write the DNS-01 TXT into cloudfront.net, which the Hostinger provider rejects
# with "no subdomain because the domain and the zone are identical". Renewal has failed
# daily since ~2026-08-11. Disabling CNAME support writes the TXT directly into the
# gummfit.com zone, where an explicit record outranks the wildcard.
export LEGO_DISABLE_CNAME_SUPPORT=true
# `run` on lego 5.x is get-OR-renew and idempotent — it only issues a new
# cert when the existing one is within --renew-days of expiry, so a daily
# cron cadence does not trip Let's Encrypt's 5-duplicate-certs/week limit.
# (Older lego had a separate `renew` subcommand for this; 5.2.2 on this host
# dropped it and folded the behavior into `run` — `lego renew` here is
# "flag provided but not defined", not a no-op. Confirmed against `lego
# run --help` on the host 2026-08-27; re-check syntax with that command if
# a future lego upgrade breaks this again.)
/usr/local/bin/lego run --accept-tos -m aaron@hey-matcha.com --dns hostinger \
  --dns.propagation.wait 180s -d gummfit.com -d "*.gummfit.com" \
  --renew-days 30 \
  --deploy-hook "systemctl reload nginx"
rc=$?
echo "[$(date)] gummfit renew cycle done (lego rc=$rc)"
exit $rc
