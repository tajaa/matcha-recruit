# Tell-Us backend

Rewards-for-feedback app. Own product, mirrors Cappe's shape — not a matcha tenant. See root `CLAUDE.md`'s "Repo layout — products map" for where this fits; this file covers specifics of `server/app/tellus/`.

## Identity & boundary

- Own identity model: `tellus_accounts` (consumer + brand), JWT `scope=tellus`. Not `users`/`companies`.
- Mounted at `/api/tellus`.
- **Import rule**: `tellus/` imports only from `app/core/*`, with **one documented exception** — `tellus/services/geo.py` reuses `matcha.services.property.property_cat.geocode` (single US Census geocoder; keep that function's signature stable, since tellus depends on it). Verified 2026-07-27: `tellus → matcha` is exactly that 1 edge. Don't add a second without updating the root CLAUDE.md count.

## Layout

- `routes/` — `auth.py`, `feedback.py`, `gamification.py`, `grants.py`, `links.py`, `marketplace.py`, `public_intake.py`, `rewards.py`, `_shared.py`
- `services/` — `auth.py`, `email.py`, `feedback_service.py`, `geo.py` (the matcha import lives here), `marketplace_service.py`, `points_service.py`
- `models/tellus.py` — Pydantic shapes

## Frontend pairing

Paired frontend is a separate Vite app at `client/tellus/` (React 19), served by the same nginx at `/tellus/`. No dedicated CLAUDE.md there yet — see root CLAUDE.md's repo-layout table.

## Cross-cutting rules

DB safety rules, test-data email domain rules, and deploy rules are in root `CLAUDE.md` — they apply here unchanged, not restated.
