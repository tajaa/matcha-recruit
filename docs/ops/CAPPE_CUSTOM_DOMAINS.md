# Cappe custom domains — CloudFront tenant runbook

How tenant-owned hostnames (`example.com`, `shop.example.com`) get TLS and reach
the Cappe renderer. Application flow and invariants live in
`server/app/cappe/DOMAINS.md`; this file is the AWS + host side, which nothing in
the repo can do for you.

**Nothing here is applied yet.** The feature is dark behind
`CAPPE_CUSTOM_DOMAINS_ENABLED` (default off): while it is off, search / purchase /
connect return 503 and the UI shows "coming soon", but tenants can still manage
domains they already own (auto-renew, DNS, transfer).

## Why tenants and not the wildcard

`gummfit.com` + `*.gummfit.com` sit behind one CloudFront distribution with one
ACM certificate (`docs/ops/CAPPE_EDGE.md`). A tenant's own domain is not covered by
that certificate, and a standard distribution carries exactly one. CloudFront
**multi-tenant distributions** solve this: one *tenant-only* distribution holds
the shared origin/WAF/behaviour config, and each custom domain is a *distribution
tenant* with its own CloudFront-managed certificate that CloudFront issues and
renews itself.

Before this, a purchased domain pointed an A record straight at the EC2. There is
no certificate for it there, so every visitor got a name-mismatch interstitial
and then the Gummfit marketing page.

## 1. Tenant-only distribution

Clone the JSON in `deploy/cloudfront/README.md` with these differences:

- `"ConnectionMode": "tenant-only"`
- no `Aliases`, no `ViewerCertificate` (tenants carry their own)
- same origin `origin.gummfit.com`, same `X-Cappe-Origin-Verify` custom header
  (**same secret** as the existing distribution — nginx checks one value)
- same `CachingDisabled` cache policy and `Managed-AllViewer` origin request
  policy (the renderer routes on the viewer `Host`)
- same WAF ACL `cappe-public-edge`

```bash
aws cloudfront create-distribution --distribution-config file://tenant-dist.json
# → record Distribution.Id as CAPPE_CF_TENANT_DISTRIBUTION_ID
```

Keep `tenant-dist.json` outside the repo; it contains the origin secret.

## 2. Connection group

```bash
aws cloudfront create-connection-group --name cappe-custom-domains --enabled
# → ConnectionGroup.Id              = CAPPE_CF_CONNECTION_GROUP_ID
# → ConnectionGroup.RoutingEndpoint = CAPPE_CF_ROUTING_ENDPOINT   (dxxxx.cloudfront.net)
```

No Anycast static IP list: it is priced for enterprises. The consequence is that
an apex domain cannot use an A record — it needs `ALIAS`/`ANAME` (CNAME
flattening). Porkbun supports `ALIAS`, which is what we write for domains we
register. A BYO tenant whose DNS host has no flattening can connect a subdomain
instead (`CNAME`).

## 3. Scoped IAM key

Do **not** reuse the admin key in `.env.backend`. Create a user whose only policy is:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "cloudfront:CreateDistributionTenant",
      "cloudfront:GetDistributionTenant",
      "cloudfront:UpdateDistributionTenant",
      "cloudfront:DeleteDistributionTenant",
      "cloudfront:ListDistributionTenants",
      "cloudfront:GetManagedCertificateDetails",
      "acm:RequestCertificate",
      "acm:DescribeCertificate"
    ],
    "Resource": "*"
  }]
}
```

Tighten `Resource` to the tenant distribution + connection group ARNs once they
exist. When the two key vars are unset the app falls back to the default boto3
credential chain.

## 4. Environment (`~/matcha/.env.backend` on the app EC2)

```
CAPPE_CF_TENANT_DISTRIBUTION_ID=E...
CAPPE_CF_CONNECTION_GROUP_ID=cg_...
CAPPE_CF_ROUTING_ENDPOINT=dxxxx.cloudfront.net
CAPPE_CLOUDFRONT_ACCESS_KEY_ID=AKIA...
CAPPE_CLOUDFRONT_SECRET_ACCESS_KEY=...
CAPPE_CUSTOM_DOMAINS_ENABLED=false     # flip LAST, step 7
```

No deploy script overwrites that file. Recreate the backend container to load it.

## 5. nginx

`deploy/nginx/cappe-custom-domains.conf` is the `:443 default_server`. CloudFront
reaches the origin with SNI `origin.gummfit.com` (covered by the gummfit
wildcard) and the **viewer's** `Host`, which matches no `server_name` — so without
an explicit default the request fell to the first block on the port, the gummfit
apex, and got the marketing SPA. The block carries the same origin gate include,
so a request that did not come through CloudFront is a 403.

It ships with the other `deploy/nginx/*.conf` on the next **non-hotfix** backend
deploy (`update-ec2.sh` `sync_nginx`; it restores the previous files if
`nginx -t` fails). Confirm on the box:

```bash
sudo nginx -T 2>/dev/null | grep -n "default_server"
```

## 6. Migration + scheduler

`zzzzcappe31` adds the edge columns and seeds `cappe_edge_sync` (off);
`zzzzcappe32` adds `cappe_edge_tombstones` (site delete writes to it, so it must be
applied before the backend that ships with it). Apply dev → prod through the
normal scripts.

## 7. Turn it on — in this order

1. Steps 1–6 done; backend recreated with the env above.
2. `CAPPE_CUSTOM_DOMAINS_ENABLED=true`, recreate the backend.
3. Admin → Settings: enable **Cappe Edge Sync**. It runs on each hourly worker
   restart. Without it a domain never leaves `pending_dns`, because the sweeper is
   the only thing that publishes (`cappe_sites.custom_domain`).
4. Register one throwaway domain end to end before telling anyone.

## Verify

```bash
# tenant exists and is deploying
aws cloudfront list-distribution-tenants --query "DistributionTenantList[].{n:Name,s:Status}"

# DNS points at the edge
dig +short example.com          # CloudFront addresses, NOT 54.177.107.107
dig +short www.example.com CNAME

# certificate
aws cloudfront get-managed-certificate-details --identifier <tenant-id> \
  --query "ManagedCertificateDetails.CertificateStatus"     # → issued

# the site, with the right certificate and the tenant's page
curl -sI https://example.com/ | head -5
```

Row state (read-only):

```bash
./scripts/prod-psql.sh -c "SELECT domain, kind, status, edge_status, edge_error, edge_checked_at
                             FROM cappe_domains ORDER BY created_at DESC LIMIT 20;"
```

| `edge_status` | Meaning | Action |
|---|---|---|
| `none` | never provisioned | sweeper adopts it; or "Set up HTTPS" in the UI |
| `provisioning` | tenant being created / deploying | wait; a claim with no tenant goes stale after 10 min and is retried |
| `pending_dns` | waiting for the tenant's DNS | they add the record shown in the UI |
| `live` | certificate issued, domain published | — |
| `failed` | see `edge_error` | "Retry setup" (replaces a tenant whose certificate died) |

## Things that will bite

- **Every name on a managed certificate must resolve to the edge** or it stays
  `pending-validation` until it times out. That is why a connected domain gets
  exactly one hostname and only a domain we registered gets `www` as well.
- **Deleting a site deletes its tenants**, durably. The tenant ids are copied into
  `cappe_edge_tombstones` in the same transaction as the delete (the cascade
  removes `cappe_domains`, the only other record of them). A fast-path attempt runs
  after the response, but CloudFront refuses to delete a tenant that is still
  deploying its disable, so that usually fails; the `cappe_edge_sync` sweeper
  drains the table and retries every cycle. A row still there after 10 attempts is
  logged at ERROR — `SELECT * FROM cappe_edge_tombstones` shows what is stuck and
  why (`last_error`). Until it drains, reconnecting that domain fails with
  "already exists".
- **Re-pointing a registered domain clears the old records first.** `point_at_app`
  deletes any A/AAAA/ALIAS/CNAME at the apex and `www` that is not already the
  edge endpoint before creating its own — a pre-edge domain carries
  `A → app IP` + `www CNAME → apex`, and either one beside the ALIAS keeps the
  certificate from validating. MX/TXT and other hostnames are never touched.
- **A transfer-out does not take the site down.** Teardown happens at `expired`.
- **Pricing/quotas**: check current CloudFront multi-tenant pricing and the
  distribution-tenant quota before onboarding in volume.

## Rollback

`CAPPE_CUSTOM_DOMAINS_ENABLED=false` and recreate the backend: creation stops,
existing live domains keep serving (they do not depend on the flag), the sweeper
stops adopting. To fully back out, disable the scheduler row and delete tenants
with `aws cloudfront delete-distribution-tenant` (disable first; needs the ETag).
