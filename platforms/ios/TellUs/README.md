# Tell-Us (iOS)

Native SwiftUI client for the Tell-Us rewards-for-feedback product. Standalone XcodeGen project — not a target inside `Matcha.xcodeproj`. Serves both account types (`consumer` and `brand`) in one binary, role-switched at login.

## Setup

```bash
brew install xcodegen   # if not already installed
make generate            # generates TellUs.xcodeproj from project.yml
make open                 # opens the generated project in Xcode
```

Do not edit `TellUs.xcodeproj` directly — it's regenerated from `project.yml` on every `make generate`. `TellUs.xcodeproj` stays committed (Xcode/CI need a project file to open), but `project.yml` is the source of truth; a hand-edit to the `.xcodeproj` (or to `Info.plist` directly — its custom keys must live under `project.yml`'s `info.properties`) is silently discarded on the next generate. Adding a new source file just means dropping it under `App/`, `Models/`, `Services/`, `ViewModels/`, or `Views/`; xcodegen picks it up automatically on the next generate (no manual pbxproj editing).

## Running against the local dev backend

The app's Debug build points at `http://127.0.0.1:8001/api/tellus` by default — the same backend `./scripts/dev-remote.sh` starts at the repo root. Override with the `TELLUS_API_URL` environment variable (Xcode scheme → Run → Arguments → Environment Variables) to point at a remote box instead.

```bash
cd platforms/ios/TellUs
make build   # xcodebuild for the simulator
make test    # unit tests (XCTest, no network — model decode fixtures + pure-function tests)
make run     # build, install, and launch on $(SIM), default "iPhone 17 Pro"
```

## Scripts

Same shape as `platforms/desktop/Espresso`'s scripts, adapted for iOS + XcodeGen:

| Script | Purpose |
|---|---|
| `./run.sh [build\|clean]` | Simulator dev loop — build (with compact error/warning output), install, launch. `SIM="iPhone 16" ./run.sh` to override the simulator. Same as `make run`. |
| `./run-prod.sh` | Same as `run.sh`, but launches with `TELLUS_API_URL` pointed at `https://hey-matcha.com/api/tellus` instead of the local dev backend. Tell-Us's API is public, so unlike Espresso's `run-prod.sh` no SSH tunnel is needed. Same as `make run-prod`. |
| `./release-appstore.sh` | Bump build number → archive → upload to App Store Connect / TestFlight. Flags: `--no-upload` (archive only), `--no-bump` (retry a failed upload without reusing a build number), `--status` (show current build + attempt history), `--set-build N` (recover from build-number drift). Same as `make release` / `make release-dry`. Requires `APPLE_API_KEY_ID` / `APPLE_API_ISSUER_ID` / `APPLE_API_KEY_PATH` — see the script's header comment for one-time App Store Connect setup. |

**XcodeGen bump mechanics**: since `project.yml` (not the pbxproj) is source of truth here, `release-appstore.sh` bumps `CURRENT_PROJECT_VERSION` in `project.yml`, runs `xcodegen generate` to regenerate `TellUs.xcodeproj`, then archives — and auto-commits both files together so a fresh checkout never regresses the build number.

Signing: `DEVELOPMENT_TEAM: 5D6TJVCPBK` in `project.yml` (same team as Espresso/Matcha), `CODE_SIGN_STYLE: Automatic`. Bundle ID `com.beetlejuse.app` (tests: `com.beetlejuse.app.tests`) must be registered under that team in the Apple Developer portal before `release-appstore.sh` can archive for device/App Store.

## v1 scope

Consumer: auth (incl. self-service password reset from an admin-minted token), QR/link intake with photo/video upload (video streams to S3 from a temp file, not held in memory), rewards home (balance/level/streak/badges/ledger), marketplace + redeem, my reviews, boards (join/feed/reply), leaderboard, direct messages (both roles), profile/location settings, notifications (60s poll — no push).

Brand: feedback dashboard + triage (status/reward/heart/reply/publish-now, "Message reporter" DM for identified feedback), board moderation (requests/held replies/posts incl. create+edit/members/team), stores + feedback-link QR management, promo campaign creation + claim QR sharing, reward-listings CRUD + redemption fulfillment, brand settings (name/reward mode/logo/intake prompts), billing status/pricing/location-count. A brand whose plan lapses (`plan_status != active`) hits a billing wall — its own screen still resolves natively now, not a bare web link.

**Web-only in v1** (native app links out via `SafeURL.open`): Stripe checkout itself (native Stripe integration is out of scope), admin console, self-serve password-reset *request* (the backend has none — resets consume admin-minted tokens only, requesting one is still admin-side).

No push notifications, no universal links/deep links, no WebSocket — the Tell-Us backend has none of that infrastructure today; the app polls `/notifications` every 60s like the web client does.

## Architecture

- `Services/APIClient.swift`, `AuthService.swift`, `KeychainHelper.swift` — adapted from `platforms/desktop/Espresso/Espresso/Services/`. Same token-refresh/retry/maintenance-detection policy; adds `APIError.paymentRequired` for the 402 wall (wired end-to-end — `AppState.handle402()` actually has a caller) and `uploadMultipart<T>` (brand logo upload).
- `App/AppState.swift` — `@Observable` session/routing orchestrator (WerkiOS idiom), single source of truth for which tab tree renders.
- One `Service` singleton per backend router (`RewardsService`, `FeedbackService`, `BoardManageService`, `DmService`, `BrandAdminService`, `BillingService`, `GamificationService`, etc.), one `@Observable` ViewModel per screen. `ViewModels/Support/LoadableVM` is the shared isLoading/error/withLoad helper most VMs adopt.
- `MediaByteLoader` caches downloaded report/review media **bytes by id**, never the URL — media URLs are presigned S3 GETs with a 15-minute TTL, re-minted on every server response. Byte-budget LRU (50MB cap); video streams via AVPlayer instead of downloading through this cache.
- Consumer tabs: Home/Market/Scan/Boards/More. Brand tabs: Dashboard/Feedback/Board/Messages/More. "More" holds the overflow screens that don't fit a 5-tab bar.
