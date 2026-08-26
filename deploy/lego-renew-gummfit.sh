#!/bin/bash
# Renew the gummfit.com wildcard cert (lego, DNS-01 via Hostinger) and reload
# nginx on success. The wildcard A re-assert runs UNCONDITIONALLY — Hostinger
# zone updates during the ACME TXT dance have been observed to drop it
# (2026-06-12), and a failed renew must not skip the daily self-heal.
set -uo pipefail
set -a; source /etc/lego/hostinger.env; set +a
export LEGO_PATH=/etc/lego
# The Hostinger zone's wildcard `* CNAME -> dburfxi3p5e15.cloudfront.net` (added for
# Cappe/CloudFront) also covers _acme-challenge.gummfit.com. lego follows that CNAME and
# tries to write the DNS-01 TXT into cloudfront.net, which the Hostinger provider rejects
# with "no subdomain because the domain and the zone are identical". Renewal has failed
# daily since ~2026-08-11. Disabling CNAME support writes the TXT directly into the
# gummfit.com zone, where an explicit record outranks the wildcard.
export LEGO_DISABLE_CNAME_SUPPORT=true
/usr/local/bin/lego run --accept-tos -m aaron@hey-matcha.com --dns hostinger \
  --dns.propagation.wait 180s -d gummfit.com -d "*.gummfit.com" \
  --deploy-hook "systemctl reload nginx"
rc=$?
# Re-assert wildcard A (idempotent; overwrite:false appends only if missing —
# NEVER set true: true replaces the whole zone including the Google MX records)
curl -s -X PUT https://developers.hostinger.com/api/dns/v1/zones/gummfit.com \
  -H "Authorization: Bearer ${HOSTINGER_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"overwrite\": false, \"zone\": [{\"name\": \"*\", \"records\": [{\"content\": \"54.177.107.107\"}], \"ttl\": 300, \"type\": \"A\"}]}" >/dev/null
echo "[$(date)] gummfit renew cycle done (lego rc=$rc)"
exit $rc
