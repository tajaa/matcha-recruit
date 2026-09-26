# Codex in Espresso

Espresso bundles Codex 0.155.1 for arm64. Fetch once before building:

```sh
cd platforms/desktop/Espresso
python3 scripts/codex-runtime.py fetch
./run.sh build
```

The archive lives in ignored `.build/codex/`. `runtime.json` pins the official
release and SHA-256. The Xcode build phase verifies the archive offline, embeds
`codex` and `codex-code-mode-host` in `Contents/Helpers`, and signs each with the
parent's identity and sandbox-inheritance entitlements before Xcode signs the
app. LICENSE, NOTICE and the version manifest live in `Contents/Resources/Codex`.
Voice, ripgrep and shell resources are omitted; research disables shell, apps,
shell snapshots and multiple agents. No user's terminal install is executed.

A Debug build without the archive remains usable but reports that local Codex
is unavailable. Release builds require the archive and `ARCHS=arm64`. Intel and
universal archives are intentionally rejected until tested. Developer ID,
notarization and App Store distribution remain unvalidated; do not release this
draft integration merely because the ad-hoc Debug build passes.

Settings → AI Connectors provides browser and device-code ChatGPT sign-in.
Codex owns its credentials under the sandbox container's
`Library/Application Support/EspressoCodex/<Matcha-user-id>`. They are isolated
from terminal Codex and from other Matcha users. Espresso reads account status
over RPC and never reads the credential file. Matcha logout stops research;
**Sign out of ChatGPT** also removes the Codex-managed login for that user.

Research cards have **Research with Codex**. One run may be active at a time,
with a 25-minute deadline. Matcha issues a 30-minute bearer for its existing MCP
resource; this is separate from ChatGPT authentication. It has the user's
research permissions, not a card-specific authorization scope. The run enables
only get/claim/attach research tools and live web search. A successful attach
result plus a refreshed card in Review with the named attachment is required
before displaying success. Cancellation never rewinds the card. Publication is
not retried automatically because attachment/note/card writes are not atomic.

Every run attempts to revoke its grant on exit, including cancellation. Cleanup
after an invalidated session or network failure may fail; the token expires
without renewal. Password changes and connector disconnect revoke it through
the existing grant machinery. No vendor token goes to Matcha's server.

## Validation and manual acceptance

Focused tests (with an available signing identity, omit the signing overrides):

```sh
xcodebuild -project Matcha.xcodeproj -scheme Matcha -configuration Debug \
  -destination 'platform=macOS,arch=arm64' \
  CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM= \
  PROVISIONING_PROFILE_SPECIFIER= \
  -only-testing:MatchaTests/CodexProtocolTests test
```

The bundled-process test uses a fresh empty credential namespace and never
signs in or edits a card. Protocol fixtures exercise fragmented Unicode,
malformed/oversized input, unknown fields and publication evidence.

Before shipping, manually verify in a disposable dev research card: browser
callback, device-code fallback, persisted account after restart, cancellation
during setup and inference, exhausted usage, invalid/expired/revoked bearer,
hostile card/web instructions, actual tool inventory, successful report attachment,
and uncertain publication recovery. Explicit approval is required before tests
write real database rows. Also validate real release identities, nested helper
signatures, notarization, installer size and App Store eligibility. The spike's
measured limitations are in `docs/plans/ESPRESSO_CODEX_APP_SERVER_SPIKE.md`.
