# Cappe Edge Protection

This runbook covers the Cappe public-site CloudFront/WAF cutover. It is not a
database migration procedure. Apply the access migration through the normal
dev-then-prod migration workflow only after the migration is committed.

## Host Policy

- Manual booking works on canonical tenant hosts and verified custom domains.
- AI booking suggestions work only on `https://<subdomain>.<CAPPE_BASE_DOMAIN>`.
- Access links are built from the stored site subdomain and
  `CAPPE_BASE_DOMAIN`; request `Host`, `X-Forwarded-Host`, and
  `X-Forwarded-Proto` are never used to construct a link.
- The suggestion session cookie is host-only, `Secure`, `HttpOnly`,
  `SameSite=Lax`, path `/`, and expires after 30 minutes.
- Access links contain a raw token only in the URL fragment. The token is
  removed with `history.replaceState` before redemption.

## DNS And ACM

Validate the ACM certificate in `us-east-1` before creating the distribution:

```text
_46f04af798bd2a046abe1c60af899754.gummfit.com
CNAME
_a458fbd9dde585dfd6425839e05b747d.jkddzztszm.acm-validations.aws
```

Create an exact origin record before changing the wildcard:

```text
origin.gummfit.com A 54.177.107.107
```

The exact `origin.gummfit.com` record must not resolve through the future
`*.gummfit.com` CloudFront record. Confirm Hostinger supports apex
ALIAS/ANAME/CNAME flattening. If it does not, use Route 53 for authoritative
DNS before cutover.

Check:

```bash
dig +short gummfit.com A
dig +short '*.gummfit.com' A
dig +short origin.gummfit.com A
aws acm describe-certificate \
  --certificate-arn "$CAPPE_ACM_CERTIFICATE_ARN" \
  --region us-east-1
```

Do not put CloudFront edge IP addresses in DNS A records.

## CloudFront Distribution

Create one distribution with these properties:

- Aliases: `gummfit.com`, `*.gummfit.com`
- ACM certificate: the validated `us-east-1` certificate for both names
- Origin: `origin.gummfit.com`
- Origin protocol: HTTPS only, TLS 1.2
- Viewer protocol: redirect HTTP to HTTPS
- Allowed methods: GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE
- Cache policy: managed `CachingDisabled`
- Origin request policy: forward viewer headers, cookies, and query strings
- Viewer `Host`: preserve and forward to nginx
- Origin custom header: `X-Cappe-Origin-Verify`
- WAF: `cappe-public-edge`
- Compression: enabled
- IPv6: enabled

Dynamic tenant HTML and all `/api/*` paths must not be cached initially. The
origin already has site-keyed Redis rendering caches. Add asset caching later
only after proving that the cache key cannot mix tenant hosts.

Use a distribution config file outside the repository for the secret-bearing
CloudFront custom header. Never commit the value.

## Origin Protection

Generate a random 256-bit value and store it in the EC2 backend environment:

```text
CAPPE_CLOUDFRONT_ORIGIN_SECRET=<random-secret>
```

Use the same value as the CloudFront origin custom header. CloudFront must
overwrite the header, not forward a viewer-provided value.

Install the secret-bearing nginx snippet from:

```text
deploy/nginx/cappe-cloudfront-origin-gate.conf.example
```

as:

```text
/etc/nginx/snippets/cappe-cloudfront-origin-gate.conf
```

Enable the snippet only on the canonical Gummfit server blocks after the
distribution is serving traffic. Do not enable it before the CloudFront origin
header is configured or the origin will reject all requests.

The origin security group should ultimately allow HTTPS only from the chosen
CloudFront origin path. If an AWS-managed CloudFront prefix-list-based rule is
not available for this setup, retain the nginx secret gate and monitor direct
origin requests until the security-group restriction is implemented.

Always validate before reload:

```bash
nginx -t
systemctl reload nginx
```

## WAF Rules

The existing ACL ARN is:

```text
arn:aws:wafv2:us-east-1:010438494410:global/webacl/cappe-public-edge/22a33df3-77c4-492b-8a21-9c6b054a17d7
```

Keep the managed AWS IP reputation and known-bad-input rules. Keep the
20-requests/5-minutes/IP rate rule scoped to:

```regex
^/api/cappe/public/sites/[^/]+/booking-suggestions$
```

Use a separate path set for access and redemption body protection:

```regex
^/api/cappe/public/sites/[^/]+/booking-suggestions/access(?:/redeem)?$
```

The current access-path regex set ARN is:

```text
arn:aws:wafv2:us-east-1:010438494410:global/regexpatternset/cappe-booking-suggestion-access-path/7d11838f-010c-468f-8586-efb2a8dd362f
```

Both body rules must require `POST` and block bodies over 8192 bytes with
oversize handling `MATCH`. Backend Redis limits remain authoritative for
per-email access requests and per-site suggestion budgets.

## Verification Before DNS

Test the distribution hostname while preserving the viewer host. Use a
temporary distribution hostname, not the public DNS records:

```bash
curl --connect-to lumiere-spa.gummfit.com:443:<distribution>.cloudfront.net:443 \
  https://lumiere-spa.gummfit.com/
```

Verify all of the following:

- Tenant A and tenant B receive different rendered HTML.
- The origin rejects requests without the CloudFront secret.
- The CloudFront request reaches nginx with the viewer `Host`.
- A direct-origin request cannot invoke the suggestion endpoint.
- An oversized suggestion or access body returns 413.
- WAF sampled requests show the intended URI matches.
- A missing session returns 403 before Gemini work.
- A valid canonical session can request suggestions.
- A custom-domain session cannot invoke suggestions.
- Manual booking works without any cookie.
- Redemption sets `Secure`, `HttpOnly`, `SameSite=Lax`, `Max-Age=1800`, and no
  `Domain` attribute.
- The access page removes its fragment before the redemption request.

## DNS Cutover

1. Confirm ACM is `ISSUED` and the distribution is `Deployed`.
2. Confirm the exact `origin.gummfit.com` record is still pointed at EC2.
3. Deploy the backend, nginx snippet, and origin environment secret.
4. Validate the distribution hostname with the preceding checks.
5. Change the apex and wildcard records to CloudFront using the DNS provider's
   supported alias/flattening mechanism.
6. Verify apex, wildcard, custom-domain behavior, API POSTs, cookies, and WAF.
7. Monitor nginx access logs, WAF metrics, CloudFront 4xx/5xx metrics, and
   suggestion rate-limit responses.

## Rollback

1. Restore the prior apex and wildcard DNS records.
2. Wait for the DNS provider's TTL and verify direct EC2 service.
3. Temporarily disable the canonical origin gate only after direct traffic is
   intentionally restored.
4. Keep the WAF and distribution in place for investigation.
5. Do not delete the ACM certificate, distribution, or WAF ACL during the
   incident window.
