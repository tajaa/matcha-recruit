# Tell-Us "Discover" — implementation plan

## Context

No way to find a business you can't already name. `PlacesView` renders nothing until 2 chars are typed (`ViewModels/PlacesViewModel.swift:37-43`) and is buried behind More → Places. Catalog is ~5 brands / 4 stores / 2 geocoded, so a Tell-Us-only directory is an empty room. iOS has zero location capability (no `CoreLocation`, no `NSLocation*` key); `tellus_stores.lat/lng` is written but **read by no query in the package**. Discovery also dead-ends in Safari (`PlacesView.swift:143-145`).

Already built and dead, reused here rather than rebuilt: `tellus_brand_follows` + `POST/DELETE /places/{slug}/follow` (`routes/places.py:169-199`), and the `followed` flag `/places/search` already returns.

Decisions: blend live Google nearby (display-only, never persisted); device GPS with city fallback; Discover replaces the Home tab; Follow is the Discover action, board join stays the capped/approval-gated one.

Port the SQL shapes from `server/app/cappe/routes/public/directory.py` — bbox + inline haversine with no `CREATE EXTENSION` (`:82-89`), `DISTINCT ON` nearest-location CTE (`:254-262`), capped uncorrelated count subquery instead of `COUNT(*) OVER ()` (`:298-311`), depth cap + own rate bucket.

---

## 1. `server/alembic/versions/tellus_app_23_discover.py`

`revision = "tellus_app_23"`, `down_revision = "tellus_app_22"`. No new tables — `tellus_brand_follows` and `tellus_stores.lat/lng` already exist. `tellus_stores` currently has **only** `ix_tellus_stores_brand`, so neither query shape below is plannable without these:

```python
def upgrade() -> None:
    op.execute("""CREATE INDEX IF NOT EXISTS ix_tellus_stores_geo
                    ON tellus_stores (lat, lng)
                 WHERE lat IS NOT NULL AND lng IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_tellus_stores_city
                    ON tellus_stores (lower(city), lower(state))""")

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tellus_stores_city")
    op.execute("DROP INDEX IF EXISTS ix_tellus_stores_geo")
```

## 2. `server/app/tellus/routes/links.py` — geocode bug fix

The store UPDATE at `:168-172` writes `city`/`state`/`zipcode`/`address` and never re-geocodes, so editing an address leaves **stale coordinates Discover would then rank on**. Add the same `geocode_location(...)` call the create path already makes at `:131-133`, writing `lat`/`lng` in the same UPDATE.

## 3. `server/app/tellus/services/google_places.py` — nearby + text search

Append alongside `autocomplete()`. Same **None-vs-`[]`** contract (`None` = unconfigured/failed, caller must not cache; `[]` = genuine empty, cacheable). Never raises.

```python
_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
_TEXT_URL   = "https://places.googleapis.com/v1/places:searchText"
_DISCOVER_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.primaryType,places.rating,places.userRatingCount"
)

def _parse_discover(payload: dict[str, Any]) -> list[dict]:
    """Pure. searchNearby/searchText JSON -> [{place_id, name, address, lat, lng,
    primary_type, rating, user_rating_count}]. Drops entries missing `id` or a
    non-blank displayName.text — same rule as _parse_autocomplete."""

async def search_nearby(lat: float, lng: float, radius_m: float,
                        max_results: int = 20) -> Optional[list[dict]]:
    # body: {"maxResultCount": n, "locationRestriction":
    #          {"circle": {"center": {"latitude": lat, "longitude": lng},
    #                      "radius": radius_m}}}
    # No includedTypes filter: searchNearby only accepts Table A types and
    # "establishment" is NOT one of them (unlike autocomplete's
    # includedPrimaryTypes). Omitting returns all nearby types, which is what a
    # discovery surface wants.

async def search_text(q: str, lat: Optional[float] = None, lng: Optional[float] = None,
                      radius_m: Optional[float] = None,
                      max_results: int = 20) -> Optional[list[dict]]:
    # body: {"textQuery": q, "maxResultCount": n,
    #        "locationBias": {"circle": {...}}}   # bias, not restriction
```

Headers on both: `{"X-Goog-Api-Key": key, "X-Goog-FieldMask": _DISCOVER_FIELD_MASK, "Content-Type": "application/json"}`, `httpx.AsyncClient(timeout=10.0)`.

**Do not pass a session token** — these are per-request Nearby/Text Search SKUs; the autocomplete session token does not apply and sending it just muddies billing. Google caps `searchNearby` radius at 50 km.

**ToS:** results are display-only and never written to `tellus_brands`/`tellus_stores`. A row materializes only through the existing `POST /places` when the user acts, which already re-resolves Place Details server-side and persists only Google's echoed `verified_place_id`. Keeps the decided posture in `server/app/tellus/CLAUDE.md` intact — pinned by a test in §7.

## 4. `server/app/tellus/services/discover_service.py` (new)

Everything unit-testable, since the app has no mock seam for services.

```python
MAX_RADIUS_KM = 50.0     # matches Google searchNearby's own cap, so a wider ask
                         # can't silently return a narrower Google set
_COORD_PRECISION = 3     # ~110 m buckets

GOOGLE_TYPE_LABELS: dict[str, str] = {
    "restaurant": "Restaurant", "cafe": "Cafe", "bar": "Bar", "bakery": "Bakery",
    "gym": "Gym", "beauty_salon": "Hair & Beauty", "hair_care": "Hair & Beauty",
    "spa": "Spa", "store": "Shop", "clothing_store": "Shop", "book_store": "Shop",
    "pharmacy": "Pharmacy", "pet_store": "Pets", "veterinary_care": "Pets",
    "car_repair": "Auto", "lodging": "Stay",
}

def discover_cache_key(lat: float, lng: float, radius_km: float,
                       q: Optional[str]) -> str:
    """Redis key. Coords rounded to _COORD_PRECISION so two users a block apart
    share one cached Google response — this rounding IS the cost control."""

def normalize_google_type(primary_type: Any) -> Optional[str]:
    """Google primaryType -> display label; unknown or non-str -> None (never
    shown). Same whitelist idiom as cappe/services/directory.normalize_category:
    the upstream can't inject an arbitrary label into our UI."""

def dedupe_google(google_rows: list[dict],
                  known_place_ids: Collection[str]) -> list[dict]:
    """Drop Google entries already represented by a Tell-Us brand. Arg order
    mirrors PlacesViewModel.dedupe(_:against:). Rows with no place_id drop too."""

def bbox_predicate(lat_param: str, lng_param: str, radius_param: str) -> str:
    """SQL fragment bounding st.lat/st.lng to a square around the point.
    greatest(cos(radians(...)), 0.01) guards the pole singularity."""

DISTANCE_SQL: str   # haversine km with $LAT/$LNG tokens the caller substitutes;
                    # ported from cappe directory.py:_DISTANCE_EXPR
```

## 5. `server/app/tellus/models/tellus.py` — additions

```python
class TellusDiscoverEntry(BaseModel):
    source: Literal["tellus", "google"]
    name: str
    slug: Optional[str] = None            # None for source="google"
    google_place_id: Optional[str] = None
    logo_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None         # google only; tellus rows use city/state
    distance_km: Optional[float] = None
    category_label: Optional[str] = None
    # tellus: our rolling-12-month window. google: GOOGLE'S OWN numbers — the
    # client labels them separately and never blends them into a Tell-Us average.
    rating: Optional[float] = None
    review_count: int = 0                 # COUNT(*), matches /places/search + /b/{slug}
    rating_count: int = 0                 # COUNT(rating) — rating is nullable, so this
                                          # is what decides whether a star is shown at
                                          # all; without it "4.5 (12)" can come off 3 ratings
    claimed: bool = False
    has_board: bool = False
    followed: bool = False
    messaging_enabled: bool = False
    intake_token: Optional[str] = None    # unclaimed tellus rows only

class TellusDiscoverPage(BaseModel):
    entries: list[TellusDiscoverEntry]
    total: int
    next_offset: Optional[int] = None
    google_attribution: bool = False      # true when any source="google" entry present
```

## 6. `server/app/tellus/routes/discover.py` (new) — mounted in `routes/__init__.py` next to `places_router`

```python
_RATE_LIMIT_CALLS, _RATE_LIMIT_WINDOW_S = 30, 60   # own bucket: a miss can cost a Google call
_MAX_DEPTH, _MAX_LIMIT, _GOOGLE_CACHE_TTL_S = 200, 24, 300

@router.get("/discover", response_model=TellusDiscoverPage)
async def discover(
    request: Request,
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lng: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=15.0, gt=0, le=MAX_RADIUS_KM),
    q: Optional[str] = Query(default=None, max_length=120),
    city: Optional[str] = Query(default=None, max_length=120),
    state: Optional[str] = Query(default=None, max_length=60),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=_MAX_LIMIT),
    authorization: Optional[str] = Header(default=None),
) -> TellusDiscoverPage:
```

Guards, in order: `check_rate_limit(client_ip(request), "tellus_discover", 30, 60)`; a half-supplied coord pair → **400** (`(lat is None) != (lng is None)`, Cappe `:183-187` — silently ignoring half a pair returns the whole country to someone who asked "near me"); `offset >= _MAX_DEPTH` → empty page; `limit = min(limit, _MAX_DEPTH - offset)`; `viewer_id = await optional_consumer_account_id(authorization)`.

**Geo query shape** (coords supplied). `escape_like(q)` as in `places.py:114`:

```sql
WITH nearest AS (
    SELECT DISTINCT ON (st.brand_id)
           st.brand_id, st.city, st.state, ({DISTANCE_SQL}) AS distance_km
      FROM tellus_stores st
     WHERE {bbox_predicate}
     ORDER BY st.brand_id, distance_km ASC
)
SELECT b.slug, b.name, b.logo_url, b.google_place_id, b.messaging_enabled,
       b.owner_account_id, n.city, n.state, n.distance_km,
       rev.rating, rev.review_count, rev.rating_count,
       EXISTS (SELECT 1 FROM tellus_boards bd
                WHERE bd.brand_id = b.id AND bd.is_active)              AS has_board,
       EXISTS (SELECT 1 FROM tellus_brand_follows f
                WHERE f.brand_id = b.id AND f.consumer_account_id = $V) AS followed,
       CASE WHEN b.owner_account_id IS NULL THEN lk.token END           AS intake_token,
       (SELECT COUNT(*) FROM (
            SELECT 1 FROM tellus_brands b2 JOIN nearest n2 ON n2.brand_id = b2.id
             WHERE {where_sql_b2} LIMIT {_MAX_DEPTH}) capped)           AS total_count
  FROM tellus_brands b
  JOIN nearest n ON n.brand_id = b.id
  LEFT JOIN LATERAL (
      SELECT ROUND(AVG(r.rating)::numeric, 1) AS rating,
             COUNT(*)         AS review_count,
             COUNT(r.rating)  AS rating_count
        FROM tellus_reports r
       WHERE r.brand_id = b.id AND r.review_state = 'held'
         AND r.publish_at <= NOW() AND r.publish_at >= NOW() - interval '12 months'
         AND r.moderation_status = 'visible'
  ) rev ON TRUE
  LEFT JOIN LATERAL (SELECT token FROM tellus_links
                      WHERE brand_id = b.id AND is_active
                      ORDER BY created_at LIMIT 1) lk ON TRUE
 WHERE n.distance_km <= $R
   AND ($Q::text IS NULL OR b.name ILIKE '%' || $Q || '%')
 ORDER BY n.distance_km ASC, rev.review_count DESC, b.name
 LIMIT $L OFFSET $O
```

Notes that matter: the review predicate is copied **verbatim** from `places.py:87-91` so counts agree with search and `/b/{slug}`. The CTE drives off `tellus_stores` so a multi-store brand matches on **any** branch (Cappe `:244-253` — filtering a per-brand `LIMIT 1` default store instead drops brands whose non-default branch is the near one, and can't use the index). The exact-circle `n.distance_km <= $R` is applied outside the CTE because the column doesn't exist inside its own WHERE.

**City-fallback shape** (no coords): swap the CTE for `LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores WHERE brand_id = b.id ORDER BY created_at LIMIT 1) n ON TRUE`, filter `EXISTS (SELECT 1 FROM tellus_stores st WHERE st.brand_id = b.id AND st.city ILIKE '%'||$C||'%')`, `distance_km` → `NULL`, `ORDER BY rev.review_count DESC, b.name`. Falls back to `account.city`/`account.state` when the params are absent, same as `marketplace.py:45`.

**Google fill** — only when `has_geo and offset == 0 and len(tellus_entries) < limit`. Page-1-only because Google paginates independently; interleaving it into offset paging produces duplicates and gaps.

```python
redis = get_redis_cache()
key = discover_cache_key(lat, lng, radius_km, q)
rows = await cache_get(redis, key) if redis else None
if rows is None:
    rows = await (search_text(q, lat, lng, radius_km * 1000) if q
                  else search_nearby(lat, lng, radius_km * 1000))
    if rows is not None and redis:                    # None = failure, never cached
        await cache_set(redis, key, rows, ttl=_GOOGLE_CACHE_TTL_S)
rows = dedupe_google(rows or [], {e.google_place_id for e in tellus_entries if e.google_place_id})
```
Google entries get `source="google"`, `slug=None`, `claimed=False`, `has_board=False`, `followed=False`, `category_label=normalize_google_type(...)`, and Google's own `rating`/`user_rating_count`. `google_attribution=True` when any survive.

Degradation: `GOOGLE_MAPS_API_KEY` unset or Google down → `search_*` returns `None` → Google section simply absent, Tell-Us rows still render, no error surfaced. Same contract as the add-a-place flow.

Materialization needs **no new endpoint** — the client posts the existing `POST /places` with `google_place_id`, which already advisory-locks, dedupes by `google_place_id` then name+city, re-resolves Details server-side, and mints the community link.

## 7. Tests — `server/tests/tellus/test_discover_logic.py` (pure, no DB)

Same shape/docstring convention as `tests/tellus/test_board_logic.py`.

```python
class TestDiscoverCacheKey:
    test_nearby_coords_share_a_key        # (34.0522,-118.2437) == (34.05223,-118.24371)
    test_distant_coords_differ            # 0.01° apart -> different key
    test_query_is_part_of_the_key         # same coords, q="tacos" vs None
    test_radius_is_part_of_the_key

class TestNormalizeGoogleType:
    test_known_type_maps_to_label         # "cafe" -> "Cafe"
    test_unknown_type_is_dropped          # "spaceship_dealer" -> None
    test_non_string_is_dropped            # None, 123, [] -> None

class TestDedupeGoogle:
    test_drops_places_already_on_tellus
    test_keeps_places_not_on_tellus
    test_empty_known_set_keeps_everything
    test_row_without_place_id_is_dropped

class TestBboxPredicate:
    test_uses_supplied_placeholders       # emitted SQL contains $4/$5/$6, no literals
    test_guards_the_pole_singularity      # contains greatest(cos(radians(  ...)), 0.01)

class TestDiscoverModels:
    test_google_entry_needs_no_slug       # TellusDiscoverEntry(source="google", name="X") ok
    test_unknown_source_rejected          # source="yelp" -> ValidationError

class TestDiscoverNeverPersistsGoogle:
    """Pins the ToS decision in code — same idiom as the likes.py/hearted_* guard."""
    def test_route_module_never_inserts_places(self):
        src = inspect.getsource(app.tellus.routes.discover)
        assert "INSERT INTO tellus_brands" not in src
        assert "INSERT INTO tellus_stores" not in src
```

DB-touching (distance ordering, follow round-trip, materialize-once) is **manual against dev** per root `CLAUDE.md` — do not auto-run.

---

## 8. iOS

### `Services/LocationService.swift` (new)
```swift
@MainActor @Observable
final class LocationService: NSObject, CLLocationManagerDelegate {
    static let shared = LocationService()
    private(set) var coordinate: CLLocationCoordinate2D?
    private(set) var status: CLAuthorizationStatus

    /// One-shot. nil when denied/restricted, on failure, or after an 8s timeout —
    /// callers fall back to the account's city. Never throws. Deliberately
    /// `requestLocation()`, never `startUpdatingLocation()` (battery).
    /// Concurrent callers all resume off one fix via a continuation array.
    func requestOnce() async -> CLLocationCoordinate2D?
}
```
`platforms/ios/TellUs/project.yml` — add `NSLocationWhenInUseUsageDescription` to `info.properties` beside the existing `NSCameraUsageDescription` (`:52`). CoreLocation is a system framework; `import CoreLocation` suffices, no `dependencies:` entry.

### `Models/DiscoverModels.swift` (new)
```swift
enum DiscoverSource: String, Codable { case tellus, google }

struct DiscoverEntry: Codable, Identifiable, Hashable {
    let source: DiscoverSource
    let name: String
    let slug: String?
    let google_place_id: String?
    let logo_url: String?, city: String?, state: String?, address: String?
    let distance_km: Double?, category_label: String?
    let rating: Double?
    let review_count: Int, rating_count: Int
    let claimed: Bool, has_board: Bool, messaging_enabled: Bool
    var followed: Bool                      // var: the follow button mutates in place
    let intake_token: String?
    /// google rows have no slug, and two brands can share a name.
    var id: String { slug ?? google_place_id ?? name }
}

struct DiscoverPage: Codable {
    let entries: [DiscoverEntry]; let total: Int
    let next_offset: Int?; let google_attribution: Bool
}
```

### `Services/DiscoverService.swift` (new) + `Services/PlacesService.swift` (extend)
```swift
final class DiscoverService {
    static let shared = DiscoverService()
    func discover(lat: Double?, lng: Double?, radiusKm: Double = 15,
                  q: String?, city: String?, state: String?,
                  offset: Int = 0, limit: Int = 12) async throws -> DiscoverPage
}

// PlacesService — wires the two dead endpoints
func follow(slug: String) async throws -> FollowedBrand      // POST /places/{slug}/follow
func unfollow(slug: String) async throws                     // DELETE /places/{slug}/follow
```
Build the query with the existing `PlacesService.queryString(_:)` (it force-encodes `+`, which Starlette would otherwise read as a space).

### `ViewModels/DiscoverViewModel.swift` (new)
```swift
@MainActor @Observable
final class DiscoverViewModel: LoadableVM {
    var isLoading = false
    var error: String?
    var entries: [DiscoverEntry] = []
    var query = "" { didSet { queryChanged() } }
    var locationDenied = false
    var showsGoogleAttribution = false

    func onAppear() async                        // requestOnce() -> load()
    func load() async                            // page 1, resets nextOffset
    func loadMore() async                        // no-op when nextOffset == nil
    func toggleFollow(_ entry: DiscoverEntry) async
    func addToTellUs(_ entry: DiscoverEntry) async -> PlaceCreateResponse?
    private func queryChanged()                  // 450ms debounce + seq guard,
                                                 // copied from PlacesViewModel:32-50
}
```
Empty query is valid here (unlike `PlacesViewModel`'s `>= 2` gate) — **the nearby list must render with no typing at all**, that is the entire point of the screen.

### Views
- `Views/Consumer/Discover/DiscoverView.swift` — new Home tab root. Nearby list on appear; search field narrows. Location denied → city-scoped results + a "Set your city" nudge into Settings. `google_attribution` → a "Some results from Google" footer.
- `Views/Consumer/Discover/DiscoverCard.swift` — actions by state:

| entry state | primary | secondary |
|---|---|---|
| tellus, claimed, `has_board` | Follow / Following | View board |
| tellus, claimed, no board | Follow / Following | See reviews (native) |
| tellus, unclaimed | Leave feedback | — |
| google | Add to Tell-Us (`POST /places` + `google_place_id`) | then Leave feedback |

- `Views/Consumer/Brand/BrandDetailView.swift` (new) — kills the Safari kick. Reviews via existing `PublicBrandService.brand(slug:)` (`GET /b/{slug}`), Follow toggle, "Request to join board" when `has_board`, Leave feedback, Message. Repoint `PlacesView.swift:143-145` and `PlacesViewModel.swift:120-123` here.
- `Views/Consumer/ConsumerTabView.swift:10-11` — Home root becomes `DiscoverView()`. `RewardsHomeView` (points/badges/activity — zero business content today) moves behind a **points pill in Discover's toolbar** next to the existing bell. Nothing lost, no 6th tab.

**No `Picker(.segmented)` and no bare `Text` in a `.frame(maxWidth:.infinity)` button** on new screens — both failure modes were just hit in `BoardManageView`. Use the `BoardTabRail` chip pattern: `.frame(height: 44)` + `.contentShape(Rectangle())` applied **after** padding.

### iOS tests
`platforms/ios/TellUs/Tests/DiscoverModelTests.swift`, mirroring `Tests/PlacesDedupeTests.swift`:
```
testGoogleEntryIdentityFallsBackToPlaceId
testTellusEntryIdentityUsesSlug
testDecodesGoogleEntryWithNullSlugAndNullDistance
testDecodesTellusEntryWithAllFieldsPresent
```

---

## 9. Verification

```bash
cd server && ./venv/bin/python -m pytest tests/tellus/test_discover_logic.py -q
cd platforms/ios/TellUs && make test
```
Migration: author → **commit** → `./scripts/migrate-dev.sh` → `MIGRATE_REHEARSAL=1` before prod.

Manual (dev-remote, `tessu2022_guest@gmail.com` / `TellUsDev2026!`):
1. Home tab, allow location → nearby list populates **without typing**; Tell-Us rows first, Google fill after, Google rows visibly attributed.
2. Deny location → city-scoped results + "Set your city" nudge. No crash, no blank screen.
3. Follow a claimed brand → `followed` flips, survives a refetch; unfollow reverses. (First-ever exercise of `tellus_brand_follows`.)
4. Tap a Google row → Add to Tell-Us → `SELECT count(*) FROM tellus_brands WHERE google_place_id = '...'` returns **1**, not one per view. Repeat the tap; still 1.
5. Tap a claimed brand → native `BrandDetailView`, no Safari.
6. Unset `GOOGLE_MAPS_API_KEY`, restart → Discover still renders Tell-Us rows, no error banner.
7. `radius_km=200` → 422 (over `MAX_RADIUS_KM`); `?lat=34` with no `lng` → 400.

## Out of scope (v1)

Fixed category taxonomy + Gemini inference + `tsvector` search (`cappe/services/directory.py`). With 5 brands categories describe nothing, and Google's `primaryType` covers the blended rows meanwhile. Revisit when name-`ILIKE` stops being enough.
