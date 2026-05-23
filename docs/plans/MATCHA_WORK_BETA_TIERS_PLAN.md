# Matcha Work — Beta tiers

## Context

Matcha Work currently shows the same surfaces (Channels, Threads, Projects, Consultations) to every user. Want two tiers:

- **Regular** (default for everyone): Channels + Threads only.
- **Beta Lite** (per-user opt-in): adds Projects.
- **Beta Full** (per-user opt-in): everything in Lite + Consultations (and any future preview surfaces — Journals, etc.).

Gate per user via existing `users.beta_features` JSONB. Admin flips flags from `/admin/individuals`.

## Server

### `users.beta_features` keys

Two new boolean keys live alongside the existing `work_onboarded` flag:

```
beta_features = {
  "work_onboarded": true,
  "matcha_work_beta_lite": true,    // unlocks Projects
  "matcha_work_beta_full": true     // unlocks Projects + Consultations + future
}
```

No migration needed — column already exists with `DEFAULT '{}'::jsonb`.

### `/auth/me` response

Already returns `beta_features` for some role paths (e.g. `auth.py:2092`). Must consistently include it on every `/auth/me` response so the desktop can read it. Add to the response shape unconditionally if missing.

### Admin endpoint

Add to `server/app/core/routes/admin.py`:

```
PATCH /admin/users/{user_id}/beta-flags
body: { "matcha_work_beta_lite"?: bool, "matcha_work_beta_full"?: bool }
```

- Auth: `require_admin`.
- Implementation: `UPDATE users SET beta_features = COALESCE(beta_features,'{}'::jsonb) || $1::jsonb WHERE id=$2`.
- Returns the updated `beta_features` blob.

### Listing endpoint update

`/matcha-work/billing/admin/individuals` (already used by `Individuals.tsx`) needs to include `beta_features` per row. One added column in the SELECT.

## Desktop

### `Models/AuthModels.swift`

Add `betaFeatures` to `MeResponse.User`:

```swift
struct User: Codable {
    let id: String
    let email: String
    let role: String
    let avatarUrl: String?
    let betaFeatures: [String: Bool]?
    enum CodingKeys: String, CodingKey {
        case id, email, role
        case avatarUrl = "avatar_url"
        case betaFeatures = "beta_features"
    }
}
```

### `App/AppState.swift`

Computed properties:

```swift
var mwBetaLite: Bool {
    let bf = currentUserBetaFeatures
    return bf["matcha_work_beta_lite"] == true || bf["matcha_work_beta_full"] == true
}
var mwBetaFull: Bool {
    currentUserBetaFeatures["matcha_work_beta_full"] == true
}
```

`currentUserBetaFeatures` reads off the cached `MeResponse.user.betaFeatures` (populated by `useMe`-equivalent on the desktop — actually fetched via `AuthService.fetchMe()` on first appear; cache it on AppState).

Hold the dict on AppState to avoid threading it through views.

### `App/ContentView.swift` sidebar gating

Replace existing fixed sections with conditional ones:

```swift
sidebarSection("Channels", ...) { ChannelsSidebarView(...) }   // always
if appState.mwBetaFull && consultationsFeatureEnabled {
    sidebarSection("Consultations", ...) { ConsultationListView(...) }
}
if appState.mwBetaLite {
    sidebarSection("Projects", ...) { ProjectListView(...) }
}
sidebarSection("Threads", ...) { ThreadListView(...) }         // always
```

### Hard URL gates

Direct selection (e.g. `appState.selectedProjectId`) still works on regular users via stale state. On `didLogin` and `didLogout`, clear `selectedProjectId` if `!mwBetaLite`.

ProjectDetailView already loads via API which 403s if needed; not strictly required to gate client-side, but cleaner.

## Admin UI

`client/src/pages/admin/Individuals.tsx`:

1. Extend `IndividualUser` interface with `beta_features?: Record<string, boolean>`.
2. Add two columns in the table: "Beta Lite", "Beta Full" — each a checkbox.
3. On toggle, `api.patch('/admin/users/{user_id}/beta-flags', { ... })` with the single key being flipped.
4. Optimistic update: flip locally, refetch on completion.

## Critical files

| File | Change |
|------|--------|
| `server/app/core/routes/admin.py` | New `PATCH /admin/users/{id}/beta-flags` endpoint |
| `server/app/matcha/routes/billing.py` (or wherever the individuals admin list lives) | Include `beta_features` in returned rows |
| `server/app/core/routes/auth.py` | Ensure `/auth/me` always returns `beta_features` (already mostly does — fill any branch that omits it) |
| `desktop/Matcha/Matcha/Models/AuthModels.swift` | Add `betaFeatures` to `MeResponse.User` |
| `desktop/Matcha/Matcha/App/AppState.swift` | Cache + expose `mwBetaLite`/`mwBetaFull` |
| `desktop/Matcha/Matcha/App/ContentView.swift` | Conditional sidebar sections |
| `client/src/pages/admin/Individuals.tsx` | Beta Lite + Beta Full toggle columns |

## Build order

1. Server admin endpoint + individuals SELECT.
2. `/auth/me` — guarantee `beta_features` on every branch.
3. Desktop `MeResponse` model + AppState cache + sidebar gates.
4. Admin Individuals UI columns.
5. xcodebuild verify; manual test: flip flag for own user → app sidebar updates after `useMe`-equivalent invalidate.

## Verification

- Default user (no beta flags) sees only Channels + Threads. Sidebar count = 2.
- Flip `matcha_work_beta_lite` from admin → sidebar gains Projects; Consultations still hidden.
- Flip `matcha_work_beta_full` → sidebar gains Consultations (still respects existing `consultationsFeatureEnabled` AppStorage toggle in Profile).
- Unflip both → sidebar drops back to Channels + Threads on next `/auth/me` refetch.
- Direct URL nav to project: API 403 if backend gate added; otherwise just empty.

## Out of scope

- Server-side gating of project/consultation API access (visibility on FE only for now). Beta features are intentionally non-secret — gating at sidebar level keeps the surface clean without locking down the routes. Separate hardening pass can add a `require_beta_lite` dep later.
- Cross-tenant beta visibility. Each user toggles own; flags don't propagate.
- Analytics on beta uptake.
