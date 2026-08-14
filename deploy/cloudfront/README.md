# Cappe CloudFront Staging

This directory contains the reproducible distribution setup. It does not run
automatically during application deploys and does not contain the origin secret.

## Prerequisites

- ACM certificate is `ISSUED` in `us-east-1`.
- `origin.gummfit.com` resolves to the EC2 origin.
- WAF ACL `cappe-public-edge` exists in `us-east-1` with `scope=CLOUDFRONT`.
- A random 256-bit value is available in the shell as
  `CAPPE_CLOUDFRONT_ORIGIN_SECRET`.
- The same value is installed in the EC2 backend environment and nginx origin
  gate before DNS cutover.

## Current Staged Distribution

The staged distribution created on 2026-08-13 is:

- ID: `E2DR5ZV7O32BE`
- Domain: `dburfxi3p5e15.cloudfront.net`
- Status at creation: `InProgress`
- Aliases: `gummfit.com`, `*.gummfit.com`
- WAF: `cappe-public-edge`

DNS has not been changed. The origin gate has not been enabled, so direct EC2
traffic remains available during validation.

## Create A Staging Distribution

The command below creates a distribution with dynamic caching disabled, all
viewer headers/cookies/query strings forwarded, POST enabled, the issued ACM
certificate, and the existing WAF ACL. It uses the secret only as an AWS
origin custom header; it is never written to this repository.

```bash
test -n "$CAPPE_CLOUDFRONT_ORIGIN_SECRET"
test -n "$CAPPE_ACM_CERTIFICATE_ARN"
aws cloudfront create-distribution --distribution-config "$(jq -n \
  --arg caller "cappe-gummfit-$(date +%s)" \
  --arg cert "$CAPPE_ACM_CERTIFICATE_ARN" \
  --arg secret "$CAPPE_CLOUDFRONT_ORIGIN_SECRET" \
  ' {
      CallerReference: $caller,
      Comment: "Cappe Gummfit public edge",
      Enabled: true,
      IsIPV6Enabled: true,
      PriceClass: "PriceClass_100",
      HttpVersion: "http2and3",
      Aliases: {Quantity: 2, Items: ["gummfit.com", "*.gummfit.com"]},
      Origins: {
        Quantity: 1,
        Items: [{
          Id: "cappe-ec2-origin",
          DomainName: "origin.gummfit.com",
          CustomHeaders: {
            Quantity: 1,
            Items: [{HeaderName: "X-Cappe-Origin-Verify", HeaderValue: $secret}]
          },
          CustomOriginConfig: {
            HTTPPort: 80,
            HTTPSPort: 443,
            OriginProtocolPolicy: "https-only",
            OriginSslProtocols: {Quantity: 1, Items: ["TLSv1.2"]},
            OriginReadTimeout: 60,
            OriginKeepaliveTimeout: 5
          }
        }]
      },
      DefaultCacheBehavior: {
        TargetOriginId: "cappe-ec2-origin",
        ViewerProtocolPolicy: "redirect-to-https",
        AllowedMethods: {
          Quantity: 7,
          Items: ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
          CachedMethods: {Quantity: 2, Items: ["GET", "HEAD"]}
        },
        CachePolicyId: "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
        OriginRequestPolicyId: "216adef6-5c7f-47e4-b989-5492eafa07d3",
        Compress: true
      },
      ViewerCertificate: {
        ACMCertificateArn: $cert,
        SSLSupportMethod: "sni-only",
        MinimumProtocolVersion: "TLSv1.2_2021",
        Certificate: $cert,
        CertificateSource: "acm"
      },
      Restrictions: {GeoRestriction: {RestrictionType: "none", Quantity: 0}},
      WebACLId: "arn:aws:wafv2:us-east-1:010438494410:global/webacl/cappe-public-edge/22a33df3-77c4-492b-8a21-9c6b054a17d7"
    }')"
```

`Managed-AllViewer` (`216adef6-5c7f-47e4-b989-5492eafa07d3`) is intentional:
the backend renderer routes tenant pages by the viewer `Host`. Do not replace
it with `Managed-AllViewerExceptHostHeader`.

## Pre-Cutover Checks

Before changing DNS:

1. Install the same secret in EC2 and enable
   `deploy/nginx/cappe-cloudfront-origin-gate.conf.example` as the real nginx
   snippet.
2. Run `nginx -t` and reload nginx.
3. Confirm the distribution reaches both the apex and wildcard server blocks.
4. Confirm a request without the origin header is rejected at nginx.
5. Confirm tenant A and tenant B do not share rendered HTML.
6. Confirm access redemption sets a Secure host-only cookie and suggestion
   requests require the cookie.
7. Confirm direct-origin requests cannot invoke AI suggestions.

Do not change apex or wildcard DNS until the distribution is `Deployed` and all
checks pass. Rollback is DNS restoration followed by disabling the origin gate
only after direct EC2 traffic is intentionally restored.
