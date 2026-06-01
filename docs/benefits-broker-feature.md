# Employee-Benefits Broker Feature — How to Use It

Two broker-facing tools that turn the existing HR/safety platform into something
an **employee-benefits broker** wants to log into:

1. **Eligibility Exceptions** (Scope 1) — an actionable task queue that catches
   two costly mistakes automatically:
   - **New-hire enrollment gaps** — someone started ≤30 days ago and still has no
     benefits enrollment (the enrollment window is closing).
   - **Termination premium leaks** — someone was terminated but is *still* carrying
     active employer health-premium deductions (you're paying for ghost coverage).
2. **Renewal Risk Radar** (Scope 2) — a portfolio view that scores each client
   **Stable / Elevated / Critical** months before the carrier's lagging claims data
   arrives, by combining payroll turnover with Matcha's own incident/safety logs.

The detection is **source-agnostic**: it reads from one normalized roster store
that is fed by **either a Finch HRIS sync or a CSV upload** — so clients without
an HRIS still work.

---

## One-time setup (engineer/admin)

1. **Apply the migration** (dev first, then prod — never auto-run against prod):
   ```bash
   ./scripts/migrate-dev.sh      # applies benefitelig01 to dev :5432
   # verify, then:
   ./scripts/migrate-prod.sh     # applies the same revision to prod :5433
   ```
   This creates `benefit_roster_entries`, `benefit_eligibility_exceptions`,
   `benefit_renewal_risk`, and seeds the (disabled) `benefit_eligibility_sync`
   scheduler row.

2. **Turn on the feature for a company** (the company-facing `/benefits/*` surface):
   set `benefits_admin: true` in that company's `companies.enabled_features` JSONB
   (admin toggle). Broker-portal rollups under `/broker/benefits/*` do **not** need
   this flag — they're gated by the broker role + the broker→client link.

3. **Enable the daily sync** once verified on dev:
   ```sql
   UPDATE scheduler_settings SET enabled = true WHERE task_key = 'benefit_eligibility_sync';
   ```
   The worker re-dispatches it on startup (~every 15 min). Until enabled, detection
   still runs on demand whenever a roster is uploaded or "run detection" is called.

---

## Getting data in (two ways)

### A) CSV (no HRIS required)
Use this for clients who don't have an HRIS connected, or whose HRIS doesn't expose
per-employee benefit/deduction data.

- In the broker portal → **Eligibility Exceptions** → **Upload roster (CSV)**:
  pick the client company, **Download CSV template**, fill it in, upload.
- Columns: `external_id, first_name, last_name, email, department, location,
  start_date, termination_date, employment_status, has_benefits_enrollment,
  employer_health_premium_monthly, gross_pay_period`.
- `has_benefits_enrollment` = `true/false`; `employer_health_premium_monthly` is the
  employer-paid monthly health premium (drives the leak estimate); dates are
  `YYYY-MM-DD`. Use only reserved test domains (`@example.com`, `*.test`) for samples.
- Uploading immediately re-runs detection + risk for that client.

### B) Finch (automatic)
If the client has a Finch HRIS connection (with the Benefits product), the daily
sync pulls the roster + per-employee benefit facts automatically. Providers without
the Benefits product degrade gracefully (unknown enrollment is treated as unknown,
not a false alarm) — fall back to CSV for those.

---

## Using it as a broker

**Log into the Matcha Broker portal** (`/broker`). Two new sidebar entries:

### Eligibility Exceptions (`/broker/benefits/eligibility-exceptions`)
- A task queue across your whole book. Terminations (leaks) sort to the top, then
  new-hire gaps by fewest days remaining.
- **New-hire cards** show a red countdown capsule ("12 Days Left to Enroll", or
  "Enrollment window CLOSED" once past 30 days).
- **Termination items** show a red "Active Premium Leak Detected" banner with the
  estimated `$/mo` leak.
- **Ping Client HR** emails the client's HR contact (from the broker client-setup
  contact, falling back to the company owner) a nudge to act. The button records the
  send so you can see it was pinged.
- **Resolve / Dismiss** clears an item from the queue. (Items also auto-resolve when
  the underlying condition clears — the new hire enrolls, or the deduction stops.)

### Renewal Risk Radar (`/broker/benefits/renewal-risk-radar`)
- Clients sorted **Critical → Elevated → Stable**, each showing turnover (with the
  delta vs. its rolling baseline), lost workdays, near-misses, and the top trigger.
- Click a client for the deep-dive modal: per-location / per-department breakdown,
  the specific triggers (e.g. "24% turnover in last 60d", "6 lost-workday incident-days"),
  and a recommendation.
- **Download Workforce Stabilization Kit** — a PDF (incident detail + recommendation)
  to present to the client before renewal negotiations.

**The risk rule:** a dimension is flagged when turnover is ≥20% above its baseline
**and/or** lost-workday incidents are ≥15% above baseline (both → *Critical*, either
→ *Elevated*). High turnover alongside rising incidents is the leading operational
indicator of a claims surge — which is why this fires ahead of carrier data.

---

## Using it as a direct client (no broker)

A company with `benefits_admin` on can self-serve via `/api/benefits/*`:
`GET /benefits/roster/template`, `POST /benefits/roster/upload`, `POST /benefits/run`
(Finch ingest + detect + risk), `GET /benefits/eligibility-exceptions`,
`GET /benefits/renewal-risk`.

---

## Where the code lives

| Piece | Path |
|---|---|
| Detection engine (ingest, detect, risk, PDF) | `server/app/matcha/services/benefits_eligibility.py` |
| Finch per-employee benefit reads | `server/app/matcha/services/finch_service.py` (`fetch_benefit_facts`) |
| Broker endpoints (`/broker/benefits/*`) | `server/app/matcha/routes/broker_portfolio.py` |
| Company-facing endpoints (`/benefits/*`) | `server/app/matcha/routes/benefits.py` |
| Nudge email | `server/app/core/services/email/broker.py` (`send_benefit_eligibility_nudge_email`) |
| Daily cron | `server/app/workers/tasks/benefit_eligibility_sync.py` |
| Migration | `server/alembic/versions/benefitelig01_add_benefit_eligibility.py` |
| Frontend pages | `client/src/pages/broker/BrokerEligibilityExceptions.tsx`, `BrokerRenewalRiskRadar.tsx` |

## Known limitations / follow-ups

- **`policy_month` is null** until benefit-plan renewal dates exist (a future
  "benefit plans" table). The radar handles null gracefully.
- **Per-department incident counts are 0** — incidents are matched to *locations*
  (via `ir_incidents.location`), not departments, so department dimensions are
  turnover-only for now.
- **Finch benefit-fact reads are unverified against a live sandbox** (no creds at
  build time) — they degrade to "unknown" on any failure; CSV is the reliable path.
- The renewal baseline is the *previous run's* value (rolling), with a sensible
  first-run default — so trend deltas stabilize after a couple of daily runs.
