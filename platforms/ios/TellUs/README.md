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

## v1 scope

Consumer: auth (incl. self-service password reset from an admin-minted token), QR/link intake with photo/video upload (video streams to S3 from a temp file, not held in memory), rewards home (balance/level/streak/badges/ledger), marketplace + redeem, my reviews, boards (join/feed/reply), leaderboard, direct messages (both roles), profile/location settings, notifications (60s poll — no push).

Brand: feedback dashboard + triage (status/reward/heart/reply/publish-now, "Message reporter" DM for identified feedback), board moderation (requests/held replies/posts incl. create+edit/members/team), stores + feedback-link QR management, reward-listings CRUD + redemption fulfillment, brand settings (name/reward mode/logo/intake prompts), billing status/pricing/location-count. A brand whose plan lapses (`plan_status != active`) hits a billing wall — its own screen still resolves natively now, not a bare web link.

**Web-only in v1** (native app links out via `SafeURL.open`): Stripe checkout itself (native Stripe integration is out of scope), Places (Google Places session tokens + honeypot), admin console, self-serve password-reset *request* (the backend has none — resets consume admin-minted tokens only, requesting one is still admin-side).

No push notifications, no universal links/deep links, no WebSocket — the Tell-Us backend has none of that infrastructure today; the app polls `/notifications` every 60s like the web client does.

## Architecture

- `Services/APIClient.swift`, `AuthService.swift`, `KeychainHelper.swift` — adapted from `platforms/desktop/Espresso/Espresso/Services/`. Same token-refresh/retry/maintenance-detection policy; adds `APIError.paymentRequired` for the 402 wall (wired end-to-end — `AppState.handle402()` actually has a caller) and `uploadMultipart<T>` (brand logo upload).
- `App/AppState.swift` — `@Observable` session/routing orchestrator (WerkiOS idiom), single source of truth for which tab tree renders.
- One `Service` singleton per backend router (`RewardsService`, `FeedbackService`, `BoardManageService`, `DmService`, `BrandAdminService`, `BillingService`, `GamificationService`, etc.), one `@Observable` ViewModel per screen. `ViewModels/Support/LoadableVM` is the shared isLoading/error/withLoad helper most VMs adopt.
- `MediaByteLoader` caches downloaded report/review media **bytes by id**, never the URL — media URLs are presigned S3 GETs with a 15-minute TTL, re-minted on every server response. Byte-budget LRU (50MB cap); video streams via AVPlayer instead of downloading through this cache.
- Consumer tabs: Home/Market/Scan/Boards/More. Brand tabs: Dashboard/Feedback/Board/Messages/More. "More" holds the overflow screens that don't fit a 5-tab bar.
