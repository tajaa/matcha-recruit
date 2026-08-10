# Gummfit iOS

Native operate-only companion for Gummfit site owners and creators. Page
editing, billing purchase, domain setup, and payout onboarding remain web
handoffs by design.

## Build and test

```sh
make generate
make build
make test
```

Set `CAPPE_API_URL` to point a debug build at a compatible Cappe API. The
default debug URL is `http://127.0.0.1:8001/api/cappe`; release builds use
`https://gummfit.com/api/cappe`.

## Manual smoke paths

- Owner: create site → configure settings → add product → publish → review order.
- Owner marketing: add subscriber → create/schedule campaign → confirm send → review form submissions.
- Creator: create profile → upload avatar/cover → add portfolio/rates → submit for review.
- Collaboration: create offer → counter/accept → submit deliverable → approve → pay on web.

Simulator availability and API credentials are required for the full E2E pass.
