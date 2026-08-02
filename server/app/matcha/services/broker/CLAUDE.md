# Broker / client risk portal — feature spec(s)

Moved verbatim from root `CLAUDE.md`'s Feature Flags table. Root keeps a one-line summary + `→ full spec:` pointer here. Default column below matches `DEFAULT_COMPANY_FEATURES` in `server/app/core/feature_flags.py`.

## `risk_profile` (default ❌)

**Client-facing risk portal** — the business's own composite **risk index** (0–100, WC + EPL + compliance weighted roll-up via `services/broker/risk_index.py`) + component breakdown + top fixes. Gates `/risk-profile` + the `/app/risk-profile` page. Same engine the broker sees at `/broker/risk-index[/{id}]` (broker-role gated, no flag). Also serves the **submission-readiness** score (`services/broker/submission_readiness.py`, `GET /risk-profile/readiness`) — a data→underwriter-ready *completeness* checklist (distinct from risk quality: "finish these N items → tighter terms"); the broker submission packet PDF carries the same readiness banner. No new tables. Default off; admin-toggle; NOT bundled.
