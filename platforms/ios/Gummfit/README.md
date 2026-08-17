# Gummfit iOS

Native operate-only companion for Gummfit site owners and creators. Merlin
page editing, schema-driven sections, theme controls, server-rendered preview,
and setup concierge are native. Canvas freeform mode, billing purchase, domain
setup, and payout onboarding remain web-only.

## Build and test

```sh
make generate
make build
make test
```

Set `CAPPE_API_URL` to point a debug build at a compatible Cappe API. The
default debug URL is `http://127.0.0.1:8001/api/cappe`; release builds use
`https://gummfit.com/api/cappe`.

## App Store release

```sh
make release-dry   # bump, archive, and validate signing; no upload
make release       # bump, archive, and upload to App Store Connect/TestFlight
./release-appstore.sh --no-push  # upload without pushing the generated build commit
```

`release-appstore.sh` requires `APPLE_API_KEY_ID`, `APPLE_API_ISSUER_ID`, and
`APPLE_API_KEY_PATH` for uploads. Use `--status`, `--no-bump`, or `--set-build N`
for release bookkeeping. The registered App Store Connect bundle ID is
`com.gummcap.app` (tests: `com.gummcap.app.tests`).

## Manual smoke paths

- Owner: create site → configure settings → add product → publish → review order.
- Owner marketing: add subscriber → create/schedule campaign → confirm send → review form submissions.
- Creator: create profile → upload avatar/cover → add portfolio/rates → submit for review.
- Collaboration: create offer → counter/accept → submit deliverable → approve → pay on web.

Simulator availability and API credentials are required for the full E2E pass.
