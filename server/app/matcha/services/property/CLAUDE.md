# Commercial property — feature spec(s)

Moved verbatim from root `CLAUDE.md`'s Feature Flags table. Root keeps a one-line summary + `→ full spec:` pointer here. Default column below matches `DEFAULT_COMPANY_FEATURES` in `server/app/core/feature_flags.py`.

## `property` (default ❌)

**Commercial property (P-side)** — the property analog of the casualty stack. Tenant **Statement of Values** (`company_property_buildings`, migration `prop01`): per-building COPE (construction/occupancy/protection/exposure) + values (building/contents/BI/replacement/insured) → **TIV**, **insurance-to-value (ITV)**, and a **COPE grade** (`services/property/property_sov.py`). Property **limits** ride the limit-adequacy engine (`line='property'`) and property **loss runs** ride loss-development (same `line`) — the 4 line whitelists widened, no new line tables. A **property component** plugs into the composite `risk_index`. **Geocoded catastrophe** (`property_building_perils` + `coastal_wind_tier`): per-building flood (FEMA NFHL) / quake (USGS) / wildfire (USFS) / wind tiers via a best-effort Celery task (`property_cat_refresh`, scheduler-gated). Broker parity: `/broker/property-portfolio`, off-platform `broker_external_property` snapshot, and a submission-packet property section. Gates `/property/*` + the `/app/property` page (+ broker property surfaces). Default off; admin-toggle; NOT bundled.
