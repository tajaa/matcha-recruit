# Gummfit (Cappe) native iOS app — `platforms/ios/Gummfit/`

## Context

Cappe (consumer brand **Gummfit**, gummfit.com; backend `server/app/cappe/` at `/api/cappe`, web `client/src/cappe/`) gets a native iOS **operate-only companion**: run your storefront from your phone — orders, bookings, inbox, catalog, marketing, publish — plus the full creator-marketplace surface. Template is the TellUs iOS app (`platforms/ios/TellUs/`, PR #155): standalone XcodeGen project, copy-and-adapt its service core, same idioms.

**User-fixed scope decisions:**
- **No page editor** (no WKWebView embed, no native block editor) — editing stays on web.
- **Both personas**: site owners AND creators.
- **No Merlin AI** (kills all SSE needs).
- All operate surfaces: orders+bookings, CRM (messages/clients/reviews/forms), catalog (products/stock/photos), marketing (subscribers/campaigns/blog).
- Billing read-only (not live server-side; App Store IAP conflict).

**Key facts verified 2026-08-07:**
- Auth shares `core/services/scoped_auth.py` with TellUs — same helper, `scope="cappe"`, rotating refresh pair, server-side revocation via `tokens_valid_after`. Client port = base path + keychain key change.
- `account_type` is SINGLE-VALUED `Literal["business","personal","creator"]`, set at signup, default `business` (`server/app/cappe/models/auth.py:17`). **Never both owner+creator** (`routes/creators.py:43` 403s non-creators; collab brand side requires `business`). No dual-mode toggle needed.
- Uploads are **multipart, not presigned**: `POST /sites/{id}/upload` field `"file"`, 5MB cap, jpeg/png/gif/webp only (no SVG — stored-XSS guard, `routes/uploads.py:44-45`). Result is a public URL string put into `image_url`-style fields. TellUs `uploadMultipart` works unchanged; **do not port** `MediaByteLoader`/presign machinery.
- No unread-count endpoint — web sums `owner_unread` from `GET /sites/{id}/threads` (`CappeSidebar.tsx:61-62`). iOS: 60s poll (TellUs `AppState.swift:102-126` pattern).
- gummfit.com apex proxies `/api/` to backend (`deploy/nginx/cappe.conf:99`), auth paths rate-limited (`:86`).
- No cappe password-reset endpoint exists (web lacks it too) — backend gap, noted, not blocking.
- Publish 422 returns structured `{message, missing:[...]}` (`routes/sites.py:377-384`); collab 409 returns `{code:"payouts_not_ready", ...}` (`routes/collab.py:687-693`) — needs extended error extraction vs TellUs.

Wire-shape authority: `client/src/cappe/types.ts` (1096 lines). Copy sources: `platforms/ios/TellUs/Services/{APIClient,AuthService,KeychainHelper}.swift`, `Services/Support/{SafeURL,ServiceCache}.swift`, `App/{TellUsApp,AppState,RootView}.swift`, `ViewModels/Support/LoadableVM.swift`, `Views/Shared/*`, `{project.yml,Makefile,Info.plist,run.sh,run-prod.sh}`.

## 1. Scaffold

`platforms/ios/Gummfit/` — TellUs `project.yml` verbatim with: `name: Gummfit`, bundle `com.beetlejuse.gummfit` (+`.tests`), `CFBundleDisplayName: Gummfit`, team `5D6TJVCPBK` (verified TellUs project.yml:16), iOS 17 / Swift 5.9. Drop `NSCameraUsageDescription` (no QR; PhotosPicker needs no key). Keep ATS localhost exception. Empty `Gummfit.entitlements`. Makefile/run.sh/run-prod.sh copied with renames; env override key `CAPPE_API_URL`. All Info.plist keys live in project.yml `info.properties` (xcodegen regenerates). Folders: `App/ Models/ Services/ Services/Support/ ViewModels/ ViewModels/Support/ Views/{Auth,Owner/<Feature>,Creator/<Feature>,Shared}/ Resources/ Tests/`.

## 2. Models (~13 files, snake_case props, plain JSONDecoder, dates/times as String — TellUs convention)

| File | Shapes (types.ts refs) |
|---|---|
| `Enums.swift` | Open-set enums w/ `.unknown` fallback: OrderStatus(365), BookingStatus(600), CampaignStatus(405), OfferStatus(937), DeliverableStatus(1010), PaymentStatus(1028), CreatorProfileStatus(886), Fulfillment(252), SiteStatus(49) |
| `AuthModels.swift` | CappeAccount(7-14 + is_platform_admin), CappeTokenResponse(16-21, `.account` not `.user`), CappeSignupResponse(26-33), request bodies (`models/auth.py:9-72`, signup carries account_type) |
| `SiteModels.swift` | CappeSite(51-80), CappeReadiness/Item(35-47, action ∈ pages\|shop\|settings), CappeSiteCreate, CappeDirectoryListing(122-134) |
| `ShopModels.swift` | CappeProduct(290-314), CappeProductInput(316-333), OptionGroup/Option(254-288), CappeStockAdjust(`models/shop.py:118-123`), CappeInventoryAdjustment(272-281), CappeDiscount(558-581) |
| `OrderModels.swift` | CappeOrder(360-384), CappeOrderItem(335-346), CappeShippingAddress(348-358), status-update/decline bodies |
| `BookingModels.swift` | CappeBookingType(495-511), CappeAvailabilitySlot(513-520), CappeBooking(590-609), CappeRequestSummary(612-624), CappeRateRule(523-544), CappeRiderItem(546-554) |
| `VenueModels.swift` | CappeLocation/Hours(448-480), CappeStaff(482-493) |
| `CrmModels.swift` | CappeThread(636-649), CappeThreadDetail(651-654), CappeMessage(628-634), CappeClient(701-714), CappeReview(691-699) |
| `MarketingModels.swift` | CappeSubscriber(388-397), CappeCampaign(399-411), CappeForm/Field/Submission(415-441), CappePost(741-753) |
| `CreatorModels.swift` | CreatorProfileMe(875-895), CreatorSocial(810-830), CreatorPortfolioItem(832-854), CreatorRate(856-873), EarningsRow(1087-1096) |
| `CollabModels.swift` | CollabTerms(941-972), Campaign(974-984), OfferListItem/OfferPage(1034-1048), OfferDetail(1066-1080), OfferRevision(986-993), OfferMessage(995-1001), Deliverable(1003-1018), CollabPayment(1020-1032), action bodies (`models/collab.py:138-171`) |
| `UploadModels.swift` | CappeUploadResponse{url}, CappeAsset |
| `BillingModels.swift` | CappeSubscription (read-only, Phase 7) |

## 3. Service core — adaptation diff vs TellUs

**APIClient.swift**: baseURL env `CAPPE_API_URL` → DEBUG `http://127.0.0.1:8001/api/cappe` → prod `https://gummfit.com/api/cappe`; webOrigin fallback `https://gummfit.com`, handoff paths `/cappe/...`. **Extend `_extractErrorMessage`** (TellUs:356-367 handles string detail only): object detail → `detail.message`; add `APIError.publishBlocked(message:missing:[String])` (422 + missing[]) and carry `detail.code` (409 payouts_not_ready, mirror `client/src/cappe/api.ts:20-31`). Keep `paymentRequired` case but **delete `onPaymentRequired` callback/wall phase** — cappe 402 is only the rider plan-gate → inline upsell alert. Everything else verbatim (coalesced refresh, GET-only transient retry, 502/503/504 handling, off-main decode, uploadMultipart field `"file"`).

**KeychainHelper.swift**: verbatim; keys `cappe.accessToken`/`cappe.refreshToken` (coexists with Tell-Us on one device).

**AuthService.swift**: signup gains `account_type`; login failure strings identical to TellUs (verified `routes/auth.py:207-229` — unverified-403 vs suspended-403 vs 401); delete updateProfile/updateLocation/resetPassword (no endpoints). `/auth/me` returns bare CappeAccount.

**Support/**: SafeURL, ServiceCache verbatim. New `ImagePrep.swift` (from TellUs MediaUploadService.prepare, photo-only): passthrough jpeg/png/gif/webp ≤5MB, oversize → downscale + jpeg(0.8), still-over throws.

## 4. Domain services (~15 singletons, `siteId` passed per call — never stored, so site switch can't race)

- **SitesService**: list/create(blank)/get/update(settings subset)/readiness/publish/directory. Publish 422 → `publishBlocked`.
- **CatalogService**: products CRUD, `adjustStock(POST .../adjust)`, inventoryLog, discounts GET/PUT(whole-set).
- **OrdersService**: list/detail/update(status+carrier+tracking)/accept/decline(reason?)/attachDeliverable(PATCH items/{iid})/receiptPDF(requestData→QuickLook/ShareLink).
- **BookingsService**: types CRUD, availability GET/PUT, bookings list/setStatus/accept/decline, `requests` (unified pending queue → Home), rateRules GET/PUT, rider GET/PUT (402 inline upsell).
- **VenueService**: locations+staff CRUD (multi-location sites).
- **MessagesService**: threads/detail(marks read)/create/post/close.
- **ClientsService**: list/upsert/delete(email — URL-encode).
- **ReviewsService**: list/setStatus(approved|hidden)/delete.
- **NewsletterService**: subscribers CRUD, campaigns CRUD + send (confirm dialog).
- **FormsService**: forms CRUD, submissions list/markRead/delete.
- **BlogService**: posts CRUD.
- **UploadService**: uploadImage(5MB)/uploadFile(25MB docs)/creatorUpload(`POST /creators/me/upload`)/assets/deleteAsset.
- **CreatorService**: me(404→create flow)/createProfile/patchProfile/submitForReview/replaceSocials/replacePortfolio/replaceRates(whole-set PUTs)/earnings.
- **CollabService**: campaigns, offers(paged), offer detail(side-aware), createOffer/counter/accept/decline/withdraw/cancel, messages, submitDeliverable/approveDeliverable/requestRevision, nudgePayment. Checkout = web handoff.
- **BillingService** (Phase 7): `GET /billing/subscription` read-only.

## 5. AppState + routing

```swift
enum Phase { case restoring, loggedOut, verifyPending(email: String), owner, creator }
```
Route on `account.account_type`: `creator → .creator`, else `.owner` (+ load sites, restore `UserDefaults("cappe.lastSiteId")`). `activeSite: CappeSite?`; nil+empty → CreateSiteView. `unreadCount` = Σ owner_unread, 60s poll paused/resumed on scenePhase. `isBusiness` gates Collabs. onUnauthorized → logout (TellUs verbatim); no 402 wall. RootView switch → OwnerRootView / CreatorTabView. Auth views ported (login, signup w/ account-type segmented control, verify-wait w/ paste-token + resend cooldown).

## 6. Tabs

**Owner** (per-site TabView, site-switcher Menu in Home toolbar):
- **Home**: site card (status pill, public URL open-in-Safari), readiness checklist (action targets: shop→Catalog tab, pages/settings→web handoff), Publish button (422 renders missing list), pending-requests queue (accept/decline inline), directory sheet.
- **Sales**: segmented Orders|Bookings. Order detail: items, shipping, accept/decline, status/carrier/tracking, attach-deliverable, receipt PDF. Booking setup: types/availability/rate-rules/rider.
- **Inbox** (badge): threads → thread view (composer, close).
- **Catalog**: products (photo/price/stock) → form (PhotosPicker→ImagePrep→uploadImage→image_url; option groups; fulfillment) + stock-adjust sheet (delta/reason/note + log). Discounts.
- **More**: Clients, Reviews, Subscribers, Campaigns (send confirm), Forms+submissions, Blog, Locations&Staff (if multi-location), Site settings subset, **Collabs (business only)** — offers timeline/counter/accept/decline/deliverable review/payments w/ "Pay on web", Account (plan pill, sign out).

**Creator**: Profile (avatar/cover/socials/portfolio/rates, status banner + submit-for-review), Deals (offers → side-aware detail, deliverable submit + proof upload, payment nudge), Earnings (rows + totals, payout setup = web handoff), Account.

**Shared**: ErrorBanner, Formatters (+ centsFormatter parity w/ `fmtCents` types.ts:807), RemoteImage (plain AsyncImage — public URLs), QLPreviewRepresentable (receipts).

## 7. ViewModels + errors

LoadableVM/`withLoad{}` verbatim; one `@MainActor @Observable` VM per screen, siteId captured at init. Testable statics: `AuthViewModel.loginFailureAction`, `PublishViewModel.blockedMessage(from:)`, `StockAdjustViewModel.preview(current:delta:)` (clamp ≥0), `OfferDetailViewModel.allowedActions(side:status:)`.

Error table: 401 refresh-retry-once→logout (verbatim) · 402 inline upsell, no wall · 403-unverified → `.verifyPending` · 422 publish → checklist highlights · 409 code-branch (payouts_not_ready) · 502/503/504 maintenance (nginx JSON detail path works) · decode/cancel/transient verbatim.

## 8. Tests (10 files mirroring TellUs Tests/)

ModelDecodeTests (Site/Product+options/Order+shipping/Booking/ThreadDetail/Readiness fixtures) · ParityModelDecodeTests (CreatorProfileMe/OfferDetail/EarningsRow/CollabTerms round-trip) · EnumFallbackTests · AuthErrorMappingTests (same server strings) · PublishGateTests (422 missing[] + string-detail fallback) · ErrorCodeTests ({code,message} extraction, HTML→nil) · ImagePrepTests · StockAdjustTests (option_id omitted when nil, clamp) · OfferActionsTests (side×status matrix) · MoneyFormattingTests (fmtCents parity, nil→$0.00).

## 9. Phasing (compiles at every boundary)

| Phase | Contents | Exit check |
|---|---|---|
| 0 | Scaffold + service core adapted + Enums/AuthModels + App trio + LoginView + placeholder roots | `make build`; login vs :8001; relaunch restores session |
| 1 | Signup(type picker)/VerifyWait/AuthVM, phase routing, SitesService, site list/create/switcher, empty tabs | creator signup → CreatorTabView; owner → sites |
| 2 | Home: readiness + publish + UploadService/ImagePrep + directory | unready 422 renders missing; publish flips status |
| 3 | Catalog: products CRUD + photo + stock + log + discounts | product w/ photo visible on tenant site |
| 4 | Sales: orders + bookings + receipt PDF + booking setup + requests queue | order lifecycle E2E vs dev backend |
| 5 | CRM: Inbox + 60s poll badge, Clients, Reviews, Venue | badge works; thread round-trip w/ public `/cappe/thread/{token}` |
| 6 | Marketing: Subscribers/Campaigns/Forms/Blog + settings | campaign send E2E |
| 7 | Creator mode + owner Collabs + billing card + polish (.refreshable, empty states, README) + `make test` | offer negotiate→deliver→approve E2E, two dev accounts |

## Out of scope (with reasons)

Page/canvas editor + Merlin + image-gen (user-fixed; removes SSE) · billing purchase/portal (not live server-side; IAP 3.1.1) · Stripe Connect onboarding + collab checkout (hosted web flows → handoff) · domains (payment+DNS → web) · CSV imports (desktop-shaped → web) · video upload (editor-adjacent) · templates gallery (blank-create native, templates web) · public Discover/creator-directory browsing (not operate) · platform-admin · push/deep links (no backend infra) · password reset (no cappe endpoint exists — backend gap).

## Verification

Per-phase exit checks above against `./scripts/dev-remote.sh` backend (:8001). Final: `make build && make test` in `platforms/ios/Gummfit/`; E2E owner loop (create site → product+photo → publish → public order from tenant site → accept → receipt) + creator loop (signup creator → profile → submit) + collab loop (business offer → creator counter/accept → deliverable submit → approve). No DB DDL involved; no prod touches.
