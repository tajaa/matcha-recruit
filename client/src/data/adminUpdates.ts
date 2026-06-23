// Product changelog shown at /admin/updates. Newest first. Add an entry here
// whenever a notable feature ships — this is the admin's "what's new + how to
// use it" reference so nothing gets lost after it's built.
//
// `setup` = operator prerequisites before the feature actually works in prod
// (env vars, migrations, third-party config). `tag` flags whether it's live or
// still needs that setup.

export type AdminUpdateTag = 'new' | 'action-needed'

export type AdminUpdate = {
  id: string
  date: string // ISO YYYY-MM-DD
  category: string // product area, e.g. 'Cappe'
  title: string
  summary: string
  whatsNew: string[] // what changed / what you can now do
  howToUse: string[] // user-facing steps in the app
  setup?: string[] // operator prerequisites before it works (optional)
  notes?: string[] // plain-language context / why it matters (optional)
  tag?: AdminUpdateTag
}

export const ADMIN_UPDATES: AdminUpdate[] = [
  {
    id: 'broker-loss-ratio',
    date: '2026-06-23',
    category: 'Broker',
    title: 'Loss Ratio tab — projected ultimate ÷ premium, per policy year',
    summary:
      'Adds the metric underwriters actually price on to the broker client view: the loss ratio (projected ultimate losses ÷ paid premium), per policy year. The projected ultimate is reused straight from the existing loss-run triangulation; the only new input is the premium the client paid the carrier, which the broker enters per line per year. Each ratio is flagged against the <60% profitability target, with a per-year account rollup across all lines. Works for on-platform and off-platform (Broker Pro) clients.',
    whatsNew: [
      'New "Loss Ratio" tab on the broker client view (next to Loss Triangle), and a Loss Ratio section on off-platform Broker Pro clients.',
      'Loss ratio = projected ultimate ÷ premium paid, shown per (line, policy year) — the way underwriters read it (a WC ratio, a GL ratio…), not blended.',
      'The broker enters the premium the client paid the carrier per line/year; the ratio recomputes instantly and is colored green (< 60%) or red (≥ 60%) against the underwriter target.',
      'A per-year account rollup sums every line\'s ultimate ÷ total premium for that year.',
      'Projected ultimate is read-only — it comes from the loss-run triangle already on file, so the ratio is grounded in the carrier loss runs, not re-keyed.',
    ],
    howToUse: [
      'Broker → Clients → open a client → Loss Triangle tab first (upload/enter at least two valuations of the same policy years so projected ultimate exists).',
      'Switch to the Loss Ratio tab → for each line/year, type the premium the client paid the carrier → the loss ratio + color flag update and persist.',
      'Read the per-year "Account rollup" for the blended all-lines ratio. Repeat on off-platform Pro clients (the same section appears on their detail page).',
    ],
    setup: [
      'Apply migration lossratio01 (new broker_loss_premiums table — the broker-entered premium). Applied to DEV; PROD pending — run migrate-prod.sh.',
      'No new flag — broker surfaces are broker-role gated. No new integration or env.',
    ],
    notes: [
      'Loss ratio is only as good as the projected ultimate — if a client has no loss runs on file the tab points back to the Loss Triangle tab.',
      'Premium is stored per (line, policy year) keyed to the loss-run periods, so it lines up 1:1 with each line\'s ultimate.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'legal-defense',
    date: '2026-06-23',
    category: 'Legal Defense',
    title: 'Legal Defense — turn your records into an attorney-ready evidence packet',
    summary:
      'For full-platform (Pro) companies — especially SMBs without in-house counsel — when a legal stressor hits (subpoena, class action, EEOC charge, audit). The admin opens a "matter", describes the allegation, and chats with a GROUNDED AI that pulls the company\'s own records across every enabled subsystem (incidents/OSHA, ER cases, compliance, discipline, training, policy acknowledgments, accommodations + the immutable audit trails) and organizes them against the matter. It exports an attorney-facing packet: a defense memo (PDF) that cites only real records + a ZIP bundle of the underlying source documents. Framing is deliberate: the AI organizes and surfaces what the records show and flags gaps — it renders no verdict.',
    whatsNew: [
      'New "Legal Defense" surface (Safety group) — create a matter, chat about it, export a packet.',
      'Grounded AI: it cites only record IDs that exist in your data (a validator drops any hallucinated citation), and the PDF appendix is rendered straight from the database rows — nothing is fabricated.',
      'Organizer, not advocate: states what the records show + flags open questions for counsel; renders no liability opinion (a company-authored "we did nothing wrong" memo would be discoverable + unprivileged).',
      'Two exports: a defense-memo PDF (allegation → what the records show → cited evidence index + per-record appendix) and a ZIP bundle of the underlying uploaded documents.',
      'Send to counsel: a token-gated, expiring share link delivers the packet to an outside attorney (no Matcha login). Optional "prepared at the direction of counsel" work-product header.',
      'Read-only over evidence; every matter, chat turn, packet generation, download, and share is audit-logged.',
    ],
    howToUse: [
      'Turn on the "Legal Defense" feature for the company (Admin → Business Features), then: Safety → Legal Defense → New matter (type, allegation, optional date range + counsel name).',
      'Chat: describe what\'s being claimed → the assistant replies with what your records show, cites them, and lists open questions. The side panel shows which records are in scope.',
      'Generate "Memo PDF" or "PDF + ZIP" → download, or "Send to counsel" for a private link.',
    ],
    setup: [
      'Apply migration legaldef01 (legal_matters / messages / packets / audit_log / share_links). Applied to DEV; PROD pending — run migrate-prod.sh.',
      'Admin-toggle the "legal_defense" feature per company (default off; full-platform / Pro). Uses the existing Gemini key (LIVE_API) for the chat and S3 for packet storage.',
    ],
    notes: [
      'It assembles + organizes the factual record to cut the hourly cost of an attorney reconstructing it — it is not legal advice, and every export carries that disclaimer.',
      'Sources degrade gracefully: a disabled or empty subsystem is simply skipped (noted), never a failure.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'ir-magic-link-voice',
    date: '2026-06-23',
    category: 'Incident Reporting',
    title: 'Magic-link intake — voice dictation + invalid-link fix',
    summary:
      'Two changes to the public, token-scoped incident-intake forms (the anonymous /report link and the per-location /intake magic link). First, voice dictation now works there too — the same "Dictate" experience as the authed create form, so a reporter on a magic link can talk their account and the AI fills the form for them to review. Second, a fix for magic links returning "Invalid link": tokens are case-sensitive but were being matched lowercased, so any link with an uppercase letter (almost all of them) failed — now matched exactly.',
    whatsNew: [
      'Voice dictation on both public intake forms (anonymous /report + per-location /intake), gated by the same ir_voice_intake admin toggle as the authed form — the form only shows "Dictate" when the company has it on.',
      'Token-scoped public parse endpoints (no login) with abuse guards: per-link + per-company rate limits (not just per-IP, which IP rotation defeats), WAV magic-byte validation before the AI call, and a burned single-use /report link no longer parses.',
      'FIX: magic links no longer return "Invalid link" — the token is now matched exactly instead of lowercased (the casing mismatch broke any link containing an uppercase letter).',
      'The ir_voice_intake and legal_defense features now appear as toggles in Admin → Business Features (they were missing from the toggle list).',
    ],
    howToUse: [
      'Generate a reporting link as usual (IR → anonymous report token, or a per-location intake link).',
      'Open the link logged-out: if the company has voice intake on, a "Dictate this report" button appears — record, and the description/date/witnesses prefill for review before submitting.',
      'Existing links that previously showed "Invalid link" now work without regenerating.',
    ],
    setup: [
      'No migration. The voice button honors the existing "ir_voice_intake" feature (admin-toggle, default off) — now visible in Business Features. The invalid-link fix is live with the deploy, no action needed.',
    ],
    notes: [
      'Voice intake never auto-creates — the reporter reviews and edits every field before submitting (it becomes a legal record).',
    ],
    tag: 'new',
  },
  {
    id: 'property-deeper-capture',
    date: '2026-06-23',
    category: 'Property',
    title: 'Property — full underwriting capture (deductibles, valuation, hazards)',
    summary:
      'Widens each building from a basic Statement of Values to the full underwriting input set, so property risk is measured on real inputs instead of estimated around the gaps. New fields feed the math directly: PML is now net of the applicable deductible, the coinsurance check uses the building\'s own coinsurance %, and ACV valuation + occupancy fire-hazards + a central-station-alarm credit move the risk score. The building editor, CSV template, and AI SOV parser all capture the new fields.',
    whatsNew: [
      'New per-building inputs: valuation basis (RCV/ACV), coinsurance %, ordinance & law (A/B/C), BI period (months), blanket-vs-scheduled, AOP + wind / named-storm / quake deductibles, roof type, wiring year, central-station fire alarm, and occupancy hazards (commercial cooking/NFPA-96, hot work, hazmat). A policy_detail JSONB holds the long tail (distances, water supply, sublimits, BI worksheet).',
      'PML is now NET OF THE APPLICABLE DEDUCTIBLE (e.g. a 10% quake deductible drops a $5M gross PML to $4M) — the insurable catastrophe loss above the retention.',
      'The coinsurance shortfall uses the building\'s own coinsurance % (not a fixed 90%).',
      'The risk score absorbs ACV valuation (weaker recovery), occupancy fire-load hazards (cooking/hot-work/hazmat, capped), and a central-station-alarm protection credit.',
      'New recommendations: move ACV → replacement cost, add ordinance & law on older buildings, and add a central-station alarm on combustible construction.',
      'Captured everywhere: the building editor gains "Valuation & policy structure" and "Occupancy hazards" sections (plus roof type / wiring / alarm under COPE); the CSV template and the AI "parse a file" path extract all the new fields too.',
    ],
    howToUse: [
      'Company → Commercial Property → ✏️ edit any building (or "Add building"): the modal now has COPE+ (roof type, wiring, central-station alarm), a "Valuation & policy structure" section (RCV/ACV, coinsurance %, ordinance & law, BI months, blanket, AOP/wind/named-storm/quake deductibles), and an "Occupancy hazards" section (cooking/NFPA-96, hot work, hazmat).',
      'Import the same fields in bulk: the CSV template now includes the new columns, and the "Parse a file (AI)" path extracts them from a carrier SOV PDF.',
      'As you fill them in, the Modeled Exposure (deductible-net PML), the coinsurance shortfall, the Property Risk Score, and the risk-improvement plan all update to reflect the real policy + hazard inputs.',
    ],
    setup: [
      'Apply migration propd01 (additive ALTER on company_property_buildings — the new columns + policy_detail JSONB). Applied to DEV; PROD still pending — run migrate-prod.sh for prop01 then propd01.',
      'No new integration or env. Existing buildings with the fields left blank score exactly as before (the new inputs only adjust the numbers once entered).',
    ],
    notes: [
      'Still directional: the damage ratios + wildfire/wind baselines remain coarse estimates; the new inputs make the retained-vs-gross and recovery picture far more accurate, but it is not a licensed cat model.',
      'Editing a building in the form preserves its policy_detail JSONB long-tail (set via CSV/parse) — the form intentionally doesn\'t blank it.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'property-risk-tooling',
    date: '2026-06-23',
    category: 'Property',
    title: 'Property risk tooling — import an SOV, see $ exposure + a risk score',
    summary:
      'Turns the Commercial Property page from a data table into business-facing risk tooling. A company imports its Statement of Values (CSV or by dropping a carrier PDF that AI parses), then sees a directional $ exposure (average annual loss, worst-case PML by peril, coinsurance shortfall), a prioritized risk-improvement plan, and a single composite Property Risk Score (0–100 / grade) it can hand to its broker and carrier. Also fixes the catastrophe data sources so seismic + wildfire actually compute.',
    whatsNew: [
      'Import a Statement of Values: download a CSV template + bulk-upload, OR upload a carrier SOV PDF/spreadsheet and Gemini extracts the buildings into a reviewable, editable list before import (lenient — it normalizes "$1.5M", "Wood Frame", "Yes", etc.).',
      'Modeled $ exposure (directional, clearly labeled — not a cat model): average annual loss, worst-case PML accumulated by peril across buildings, and the coinsurance shortfall implied by under-insurance.',
      'Risk-improvement plan: a prioritized, actionable fix list (sprinkler the combustible building → projected COPE lift, true up insurance-to-value → $ shortfall, review the named-storm deductible, refresh an aged roof, document NFPA-96 hood cleaning for kitchens).',
      'Composite Property Risk Score: a per-building and TIV-weighted portfolio 0–100 score + grade + risk level, with the drivers that moved it and the top risk contributors — the underwriting headline. Also rendered in the broker submission packet.',
      'Catastrophe sources fixed: the USGS seismic endpoint had relocated (it was silently returning ZERO quake for every property — now restored platform-wide); wildfire now resolves from a conservative state/county baseline because the free per-address WHP services are now access-blocked.',
    ],
    howToUse: [
      'Company → Commercial Property → "Import": use the CSV tab (download template → fill → upload) or the "Parse a file (AI)" tab (drop a PDF/CSV → review/edit the parsed buildings → Import).',
      'The page then shows the Property Risk Score headline (+ top contributors), a Modeled Exposure card (AAL / worst PML / coinsurance shortfall), the Risk-improvement plan, and a per-building Risk grade column — expand a row for that building\'s score, drivers, and the four perils.',
      'Catastrophe (and therefore PML/AAL) populate once buildings are geocoded — provide full street addresses; the background refresh fills flood/quake/wildfire/wind.',
      'Broker submission PDF now carries the property risk score + exposure + the top fixes automatically when the client has buildings.',
    ],
    setup: [
      'No new migration for this milestone — it builds on the existing property feature (migration prop01) and the "property" feature flag. Apply prop01 in PROD if not already (still pending per the prior Property update).',
      'Catastrophe geocoding uses free gov APIs (US Census + FEMA + USGS) — no key; wildfire is a built-in state/county baseline. The SOV PDF parse uses the existing Gemini key (LIVE_API).',
    ],
    notes: [
      'Everything $-valued is a DIRECTIONAL estimate (coarse damage ratios + coarse wildfire/wind baselines), labeled as such — useful for relative risk + underwriting conversations, not a substitute for a licensed cat model. The ratios/baselines are tunable against real loss data later.',
      'The quake fix is the high-impact one: any company with property in a seismic state was scoring zero earthquake exposure before — the composite risk index, exposure, and submission packet were all undercounting it.',
      'Voice-style "best-effort" throughout: a failed parse or a down catastrophe source degrades gracefully (no data / pending) and never blocks the page or 500s.',
    ],
    tag: 'new',
  },
  {
    id: 'ir-voice-intake',
    date: '2026-06-23',
    category: 'Incident Reporting',
    title: 'Voice dictation — talk in an incident, AI fills the form',
    summary:
      'Optional "Dictate" on the incident-report form: the reporter speaks an account, one Gemini call transcribes it and extracts the fields, and the form is pre-filled for the reporter to review and edit before submitting. Never auto-creates (it stays a reviewed legal record). One shared form, so all IR products get it (full Matcha, Matcha-X, Matcha-lite).',
    whatsNew: [
      'A "Dictate" button on the Report-Incident form (shown only when the ir_voice_intake flag is on). Record → stop → one Gemini multimodal call transcribes + extracts.',
      'Pre-fills description, reporter name, date/time text, witnesses, and the best-match location; shows a read-only suggested incident type & severity (the post-submit classifier still finalizes those).',
      'Only fills fields the model actually heard — anything you already typed is preserved; you review/edit everything, then submit normally.',
      'Audio is captured via the existing PCM worklet and assembled to WAV in the browser (Gemini accepts WAV; it rejects the webm/opus that the default recorder produces).',
    ],
    howToUse: [
      'Enable: Admin → toggle the company\'s "ir_voice_intake" feature (off by default).',
      'In the Report-Incident form → click "Dictate", allow the mic, speak the incident ("Yesterday around 3pm Jane Doe slipped on a wet floor in the main warehouse, Bob Smith saw it"), click Stop.',
      'Review the pre-filled fields (edit anything), then Submit Report as usual.',
    ],
    setup: [
      'Turn on the ir_voice_intake feature flag per company (admin toggle / enabled_features). No database migration — it\'s flag-only.',
      'Uses the existing Gemini key (LIVE_API); no new integration. The reporter\'s browser must allow microphone access.',
    ],
    notes: [
      'AI-assisted + best-effort: a failed/unclear recording degrades to "please type the details" and never blocks the form or 500s; nothing is ever auto-submitted.',
      'Final incident type/severity are still decided by the existing post-insert classifier — the voice "suggested" badge is only a hint.',
      'Works in any modern browser that grants getUserMedia + AudioWorklet (Chrome/Edge/Safari/Firefox).',
    ],
    tag: 'action-needed',
  },
  {
    id: 'commercial-property',
    date: '2026-06-22',
    category: 'Property',
    title: 'Commercial Property — full P-side (SOV, geocoded catastrophe, broker parity)',
    summary:
      'Adds the property side of P&C at parity with casualty. A company keys its buildings (a Statement of Values); we compute total insured value, insurance-to-value, and a COPE construction grade, geocode each building for flood/quake/wildfire/wind exposure, fold a property component into the composite risk index, and give brokers a Property Book + a property section in the submission packet. Property limits + loss runs reuse the existing limit-adequacy and loss-development engines via a new "property" line — no new line tables.',
    whatsNew: [
      'Tenant Commercial Property page: per-building Statement of Values (COPE — construction / occupancy / protection class / year / roof / sprinklers — + building/contents/BI/replacement/insured values) → TIV, insurance-to-value (ITV underinsurance flag), and an A–D COPE grade per building + a company rollup.',
      'Geocoded catastrophe per building: address → lat/lng (US Census) → flood zone (FEMA NFHL), seismic (USGS), wildfire (USFS), and a coarse coastal wind tier; expand any building row to see the four perils. Runs in the background, best-effort.',
      'Property component in the composite risk index: COPE quality penalized by under-insurance and (capped) catastrophe tier. Presence-gated — a client with no buildings scores exactly as before.',
      'Property limits ride Limit Adequacy and property loss runs ride Loss Development (line="property") — the same engines, no duplication.',
      'Broker: a "Property Book" portfolio (TIV / COPE / ITV / worst-cat per client), an off-platform external-client property summary (view + edit on the external client), a Property section in the submission PDF, and a property submission-readiness checklist.',
    ],
    howToUse: [
      'Enable: Admin → toggle the company\'s "property" feature (it\'s off by default, not bundled).',
      'Company → Commercial Property → "Add building": enter the address + COPE + values. TIV / ITV / COPE compute immediately; the catastrophe column shows "pending" until the background geocode runs, then expand the row to see flood/quake/wildfire/wind.',
      'Broker → "Property Book": per-client TIV / COPE / ITV / cat across the book (worst COPE + biggest TIV first). For off-platform clients, open the client → "Commercial Property" card → "Add property" to key a summary.',
      'The broker submission PDF now carries a Property section automatically when the client has buildings.',
    ],
    setup: [
      'Apply migration prop01 (company_property_buildings + property_building_perils + coastal_wind_tier seed + broker_external_property + the property_cat_refresh scheduler row). Applied to DEV; PROD still pending (run migrate-prod.sh).',
      'Turn on the "property" feature flag per company (admin toggle).',
      'For catastrophe to populate: enable the property_cat_refresh row in scheduler_settings (default off). Endpoints are free US-gov APIs (Census/FEMA/USGS/USFS); override via CENSUS_GEOCODER_URL / FEMA_NFHL_URL / USGS_DESIGNMAPS_URL / USFS_WHP_URL / CAT_FETCH_TIMEOUT_S / CAT_FETCH_ENABLED if needed.',
    ],
    notes: [
      'Catastrophe is directional + best-effort: point-in-time reads of public hazard layers + a coarse state/county wind tier (no per-address wind API). A failed lookup writes an error row and the building still saves — it never 500s a page.',
      'Property loss-development is a broker surface (the loss-run table is broker-keyed; a tenant has no broker_id).',
      'Deferred (backend ready): a property tab inside the on-platform BrokerClientDetail and a standalone property.pdf — property already appears in the main submission packet.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'emr-trajectory-automation',
    date: '2026-06-22',
    category: 'Broker',
    title: 'Experience-Mod trajectory — auto worksheet capture + directional proxy',
    summary:
      'Automates the experience-mod (EMR) trajectory that brokers used to hand-key on the WC tab. Two free data sources replace manual entry: the broker uploads the bureau experience-rating worksheet PDF and we extract the REAL mod, and we auto-compute a directional proxy from loss-runs ÷ expected losses so the trend fills in even between worksheets. No licensed feed required.',
    whatsNew: [
      '"Upload worksheet" on the WC tab → Gemini extracts the published mod (+ effective date, carrier) from the NCCI / state-bureau worksheet; the broker confirms, and it saves tagged source="worksheet".',
      'Directional proxy trajectory: incurred (wc_loss_runs) ÷ expected losses (Σ class payroll × pure-premium rate), one point per loss-run valuation, drawn as a sparkline with a dashed 1.0 baseline.',
      'Every mod row is now tagged manual / worksheet (with the proxy series tagged proxy) so real vs estimated is never ambiguous to carriers.',
      'Reuses the loss-run PDF-parser pattern + the class-exposure expected-loss math already on file — no new external integration.',
    ],
    howToUse: [
      'Broker → client → Workers’ Comp tab → "Upload worksheet": drop the bureau experience-rating worksheet PDF, review the extracted mod, Save (lands as a worksheet-sourced point).',
      'The directional-proxy panel appears automatically once the client has WC class-payroll exposures + loss-runs on file; the manual "Record mod" entry still works.',
    ],
    notes: [
      'The proxy is directional (actual-vs-expected losses), NOT the bureau’s published mod — labeled as such. A true auto-calculated mod needs licensed NCCI rating tables (ELRs/D-ratios/ballast); a live feed needs NCCI CertiFlex / a carrier API / an aggregator (Verisk, LexisNexis) — both are paid follow-ons. Worksheet-parse + proxy get most of the value for $0.',
    ],
    setup: [
      'Apply migration wcmodsrc01 (adds company_wc_mods.source) — load-bearing: mod_trajectory/latest_mods now SELECT it, so the WC detail + submission + risk-index 500 without it.',
      'To see the proxy, a client needs WC class-payroll exposures + loss-runs (seed_emr_payequity_demo.sql seeds Bags for the demo book).',
    ],
    tag: 'action-needed',
  },
  {
    id: 'pay-equity-report-depth',
    date: '2026-06-22',
    category: 'Workforce Compliance',
    title: 'Pay-equity study — deeper, actionable client report',
    summary:
      'The within-role pay-dispersion study used to surface only a headline "% of roles flagged." It now returns the full per-role breakdown and a concrete remediation dollar figure, so the client report is something a business can act on — without any new data (it reads the payroll already on file).',
    whatsNew: [
      'Per role: median, min–max with a distribution bar, quartile spread (IQR, robust to one outlier), count paid below the role’s pay band, a per-role remediation cost, and an ok/watch/flag severity tier.',
      'Company rollups: total annualized payroll, median role spread, employees below band, share of payroll in flagged roles, and a headline remediation estimate (the $ to lift everyone below 80% of their role median up to it).',
      'Live compute-only preview (GET /pay-equity/analyze) renders the deep report on load WITHOUT logging a study row; "Run analysis" still logs one and now records the remediation figure in the note.',
    ],
    howToUse: [
      'Company → Workforce Compliance → Pay-equity studies: the deep report renders automatically from payroll (rollup strip + per-role table + distribution bars).',
      'Click "Run analysis from payroll" to also log it as a dated study (flips the EPL pay-equity factor to data-derived).',
    ],
    notes: [
      'This is a within-role dispersion screen, not a protected-class pay-gap audit — true adjusted/regression gaps need gender/race/tenure demographics we don’t hold (an HRIS pull would unlock them). No new schema; reads employees.pay_rate.',
    ],
    setup: [
      'Enable the workforce_compliance feature for the company; needs ≥2 employees sharing a job title with pay on file (seed_emr_payequity_demo.sql enables it + seeds dispersion for Sea Cafe).',
    ],
    tag: 'new',
  },
  {
    id: 'driver-risk-fleet-mvr',
    date: '2026-06-22',
    category: 'Broker',
    title: 'Driver Risk — fleet MVR scoring (commercial-auto entry)',
    summary:
      'Lifts MVR tracking out of the healthcare-only Resident-Care vertical into a standalone Driver Risk surface any employer with drivers can use, and adds scoring: each driver is graded clean / marginal / high-risk from license status + moving violations + at-fault accidents + major violations, rolled up to an A–D fleet grade. Driver/fleet risk is the #1 commercial-auto underwriting input — this is the cheapest beachhead into the auto line.',
    whatsNew: [
      'New /app/driver-risk page: add/track drivers, per-driver risk tier + points, fleet grade (A–D), tier counts, and overdue-MVR flags.',
      'Scoring engine: suspended/expired license, a major violation, 2+ at-fault accidents, or 4+ moving violations = high-risk; any accident/violation/flag/unknown-license = marginal; else clean.',
      'Insurer-facing Driver-Risk PDF for the commercial-auto application.',
      'Reuses (does not duplicate) the existing mvr_reviews table — migration driverrisk01 adds the scoring columns; Resident-Care keeps its MVR currency view on the same rows.',
    ],
    howToUse: [
      'Enable the driver_risk feature for the company in /admin/features.',
      'Company → Driver Risk → "Add driver": record license status, last MVR date + next-due, moving violations, at-fault accidents, and whether there was a major violation.',
      'Read the fleet grade + high-risk count; download the Driver-Risk PDF for the auto submission.',
    ],
    notes: [
      'Directional — tiers come from employer-recorded MVR data, not a pulled motor-vehicle record (an automated MVR pull needs a paid provider like Checkr/Samba; possible future integration). The scoring + tracking is the moat-cheap core; the auto line is otherwise un-served by the app.',
    ],
    setup: [
      'Apply migration driverrisk01 to prod (adds scoring columns to mvr_reviews).',
      'Deploy backend + frontend; enable driver_risk per company.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'bls-injury-rate-benchmark',
    date: '2026-06-22',
    category: 'Broker',
    title: 'Real BLS injury-rate benchmarks by detailed NAICS (#22)',
    summary:
      'Replaces the 17 hardcoded 2-digit sector injury-rate medians with ~1,000 real BLS SOII (2024) rates at 2–6 digit NAICS granularity. A client’s TRIR/DART now benchmarks against its actual industry, not a coarse bucket — e.g. nursing care (NAICS 6231, TRC 6.3) instead of the whole health-care sector (62, ~4.4). Sharpens the benchmark across WC metrics, the risk index, and the submission packet.',
    whatsNew: [
      'BLS SOII Table 1 (2024) parsed into a static rate table — ~1,000 NAICS codes with total-recordable (TRC) + days-away/restricted/transfer (DART) rates per 100 FTE.',
      'wc_benchmarks.lookup_benchmark now resolves the most detailed NAICS available (explicit code → finer industry-text map → 2-digit sector) and walks up to the sector if a code has no published rate; results carry a "source" of the real BLS year.',
      'Premium-impact + severity-band math unchanged (sector stays 2-digit); benchmark numbers are now real + sourced instead of approximate hardcoded medians.',
      'Free/public source (BLS), parsed offline; no new tables, no migration, no access risk.',
    ],
    howToUse: [
      'Automatic — WC benchmarking (broker WC tab, risk index, submission packet) uses the BLS-backed numbers once deployed.',
      'For verticals with big intra-sector swings (nursing, hospitals, trucking, restaurants) the benchmark is now materially more accurate.',
    ],
    notes: [
      'Today the finer NAICS comes from mapping the company’s industry text to a subsector (INDUSTRY_TO_NAICS) plus the 2-digit sector fallback. Capturing a company’s real NAICS (e.g. from HRIS) would unlock full 6-digit precision automatically — the lookup already accepts an explicit naics.',
      'BLS data is free + public but its site bot-blocks scraping, so the Table 1 file is downloaded by hand and parsed offline into a generated module (committed); re-run scripts/wc_data/build_bls_rates.py to refresh each year.',
    ],
    setup: [
      'Deploy backend (the generated BLS rate module ships in the image — no DB seed needed).',
    ],
    tag: 'action-needed',
  },
  {
    id: 'real-ca-wc-class-codes',
    date: '2026-06-22',
    category: 'Broker',
    title: 'Real California WC class codes + advisory pure premium rates (~494)',
    summary:
      'Replaces the ~10 illustrative demo class codes with the full California WC classification list (~494 codes) and their WCIRB advisory pure premium rates. The WC class-code viewer + the job-title→class-code mapper (wc_classmap) now run on real CA data instead of placeholders.',
    whatsNew: [
      '~494 CA class codes with descriptions + advisory pure premium rate per $100 of payroll (state=CA, source="WCIRB 9/1/2026 advisory pure premium"); demo US rows left intact.',
      'Sourced free + public: descriptions from the CA DIR/DWC class-code mirror (no login), rates from the WCIRB Sep 1 2026 Pure Premium Rate Filing (advisory pure premium delimited file).',
      'Reproducible tooling: server/scripts/wc_data/ holds the raw sources, a build script (join → combined CSV), a seed script, and a README. No schema/migration — table + admin import endpoint already existed.',
    ],
    howToUse: [
      'Admin → WC Rate Data: filter by state = CA to see the real codes + rates (the viewer you flagged as thin now has ~494 rows).',
      'These feed the broker WC class-exposure mapper (job titles → NCCI/CA codes) and per-class payroll exposure.',
    ],
    notes: [
      'California only. CA has its own rating bureau (WCIRB), independent of NCCI — its codes/rates are publishable. NCCI (most other states) is licensed/paid and is NOT included; other independent-bureau states (NY/NJ/PA/MI/WI) publish their own files if we expand.',
      'base_rate here is WCIRB’s advisory pure premium rate (loss cost, no expense loading) — directional for the viewer, not a quote; labelled via the source field, distinct from an NCCI manual rate.',
    ],
    setup: [
      'Prod: upload server/scripts/wc_data/ca_wc_class_codes_2026.csv via Admin → WC rates → import class codes (POST /admin/wc-rates/class-codes). No deploy needed — data only.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'tort-wc-presumption-tracker',
    date: '2026-06-22',
    category: 'Broker',
    title: 'Tort-reform & WC-presumption legislation tracker',
    summary:
      'Extends the existing Legislation Watch engine (RSS → Gemini → per-account alerts) beyond labor law to the casualty-relevant legal changes that move loss costs: tort reform, workers’-comp presumptions, and commercial-auto liability. Affected clients get a proactive alert in their state before the change shows up in claims.',
    whatsNew: [
      'Three new tracked categories: tort_reform (damage caps, non-economic/punitive damages, litigation funding, joint-and-several liability, premises/negligence standards), wc_presumption (firefighter cancer, first-responder/healthcare PTSD or COVID, occupational-disease presumptions), and auto_liability (commercial-auto minimum limits, negligent entrustment, vicarious liability).',
      'RSS relevance scorer + the Gemini classifier now recognize these — items on existing state DOL/L&I/legislature feeds that touch them are caught, classified, and routed to companies operating in that state (reuses compliance_alerts + per-location targeting).',
      'Alerts surface on the company Compliance → Alerts tab with friendly category labels (Tort reform / WC presumption / Auto liability).',
      'Pure engine extension — no new tables; runs on the existing legislation_watch scheduler.',
    ],
    howToUse: [
      'Enable the "Legislation Watch (RSS)" scheduler in admin (it’s default-off) so the cycle runs.',
      'Company → Compliance → Alerts: tort/WC-presumption/auto items appear alongside labor-law alerts, tagged by category and state, with a "what to do" action line.',
      '(Optional) Add state legislature RSS feeds in the feed sources for fuller tort/auto coverage — WC-presumption items already flow from existing L&I/DOL feeds.',
    ],
    notes: [
      'Why this exists — two kinds of legal change swing casualty exposure: (1) Tort reform: laws that raise or lower how easily plaintiffs win and how big verdicts get (repealing damage caps, expanding who can be sued) → bigger GL/auto/umbrella claims; the engine behind "nuclear verdicts." (2) WC presumptions: laws that auto-presume certain injuries/illnesses are work-related (firefighter cancer, first-responder PTSD/COVID) so WC pays without the worker proving it → more compensable claims, higher loss costs.',
      'Why it matters — a broker’s value is partly "I saw this coming." A new presumption or a damage-cap repeal in a state where the client operates changes their loss cost months before it hits claims. Surfacing it first lets the broker advise before renewal (raise limits, tighten controls, re-reserve) and proves ongoing value between renewals. Alerts are per-account: only states the client actually operates in (we have their locations).',
      'Honest caveat — this is an intelligence feed, not a data-moat deliverable like Proof-of-Controls / Limit-Adequacy / Loss-Dev. It doesn’t turn our owned HR data into terms; any broker could read the same laws. Its edge is aggregation + per-account targeting + that it’s free to build on rails we already had. It’s the forward-looking complement to the backward-looking loss-development triangles.',
    ],
    setup: [
      'Deploy backend + frontend.',
      'Enable the legislation_watch scheduler_settings row (default off).',
      '(Optional) Curate additional state legislature RSS feed sources for tort/auto bills.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'loss-run-triangulation',
    date: '2026-06-22',
    category: 'Broker',
    title: 'Loss-run triangulation (development factors + projected ultimate losses)',
    summary:
      'A single loss run is one snapshot — claims grow after they’re reported. This lines up the same policy years valued at multiple dates into a triangle, computes age-to-age development factors (chain-ladder), and projects ULTIMATE losses per policy year. The gap from reported-incurred to ultimate is adverse development — the reserve-adequacy signal underwriters price on. Built from the client’s own loss runs; no licensed benchmark data needed.',
    whatsNew: [
      'New "Loss Triangle" tab on the broker client detail: incurred-development triangle (policy year × valuation age), age-to-age factors, projected ultimate + adverse development per year and in total.',
      'Add loss runs by uploading the carrier PDF (Gemini extracts valuation date + per-policy-year paid/reserved/claims for you to confirm) or by keying them manually. Each upload = one valuation date; two+ valuations of the same years build the triangle.',
      'Works for on-platform (tenant) clients and off-platform Broker Pro clients; line field carries WC / GL / auto (GL & auto schemas supported).',
      'A Loss-Development section now rides the broker submission packet PDF, plus a standalone loss-development.pdf per client.',
      'New wc_loss_runs table (migration lossdev01); chain-ladder engine in services/loss_development.py (9 unit tests).',
    ],
    howToUse: [
      'Broker → client detail → Loss Triangle tab → "Add loss run": upload each historical carrier loss run (or enter manually), set its as-of date, confirm the policy-year figures, Commit.',
      'After two+ valuations the triangle, factors, and projected ultimates appear; download the Loss-dev packet, or generate the full submission PDF (it now includes the section).',
    ],
    setup: [
      'Apply migration lossdev01 to prod (wc_loss_runs).',
      'Deploy backend + frontend.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'limit-adequacy-contract-review',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Limit adequacy & contract review (carried limits vs. what contracts require)',
    summary:
      'Turns two owned inputs — the limits a company carries + the insurance requirements its contracts impose — into a concrete deliverable: "you carry $1M GL but a customer contract requires $2M." Contracts are uploaded as PDFs; Gemini extracts the required limits + endorsements for the company to confirm (the PDF itself isn’t stored). Where no contract speaks, a directional size/venue baseline flags lines that look light — labelled a starting point, not a peer benchmark or quote.',
    whatsNew: [
      'New "Limit Adequacy" surface (/app/limit-adequacy): record carried limits per casualty line (GL, auto, umbrella, WC/EL, EPL, professional, cyber) incl. additional-insured / waiver-of-subrogation / primary-&-noncontributory.',
      'Upload a contract PDF → Gemini extracts the required limits + endorsements into an editable draft you confirm; or add a contract manually. Requirements stored as JSONB; the PDF is parsed and discarded.',
      'Adequacy engine diffs carried vs. the highest contract requirement vs. a heuristic baseline → status per line (No coverage / Shortfall / Low / OK) + endorsement-gap flags.',
      'Broker: a "Limits" tab on the client detail + a Limit-Adequacy section in the submission packet PDF + GET /broker/clients/{id}/limits.pdf|limit-adequacy. Tenant clients only (needs carried/contract data).',
      'Export a standalone Limit-Adequacy review PDF from the company page.',
    ],
    howToUse: [
      'Enable the limit_adequacy feature for the company in /admin/features.',
      'Company → Limit Adequacy: under "Your coverage" enter the limits you carry per line; under "Contracts" upload a contract PDF (or add one manually) and confirm the extracted requirements.',
      'Review the "Coverage line adequacy" table for shortfalls; download the Review PDF.',
      'Broker → client detail → Limits tab: see the same diff + download the Limits packet; it also rides the main submission PDF.',
    ],
    setup: [
      'Apply migration limadq01 to prod (company_coverage_lines + company_contracts).',
      'Deploy backend + frontend (new services/routes/pages).',
      'Enable limit_adequacy per company in /admin/features.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'exclusion-gap-registry',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Grounded exclusion-gap analysis (PFAS, A&M, biometric, silent-cyber/AI…)',
    summary:
      'Replaces the old free-gen coverage-gap (which invented Cyber/Umbrella gaps with no backing data) with a curated registry of REAL emerging casualty exclusions, matched to the client from data we own — industry, operating states, and mitigation signals (biometric consent, abuse-prevention/infection-control programs, AI-hiring audits, MVR data).',
    whatsNew: [
      '9-exclusion registry (PFAS, abuse & molestation, biometric/BIPA, TBI, wildfire, silent-cyber, silent-AI, communicable disease, assault & battery) — each mapped to the lines it hits, why it’s hardening, and the mitigation.',
      'Grounded matcher: relevance from industry keywords + operating state (wildfire) + owned signals; status exposed / monitor / mitigated (mitigated = the control is documented).',
      'Surfaced as a "Coverage Exclusion Exposure" section in the broker submission packet PDF + a card on the Risk Profile portal (GET /risk-profile/exclusions). Off-platform Broker Pro uses industry + state.',
      'Over-build fix: the AI coverage-gap prompt is now grounded on this registry and told not to invent coverage lines with no supporting data.',
    ],
    howToUse: [
      'Company → Risk Profile: the Coverage exclusion exposure card lists each emerging exclusion + status + mitigation.',
      'Broker → generate a client submission PDF: the Coverage Exclusion Exposure section appears with the venue + controls sections.',
    ],
    setup: ['None — no migration, no new flag (rides risk_profile + broker submission). Deploy backend + client build.'],
    tag: 'new',
  },
  {
    id: 'venue-severity',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Venue / nuclear-verdict severity — casualty exposure dimension',
    summary:
      'Where a company operates is the single biggest severity lever in casualty (nuclear verdicts, social inflation). We already hold the exposure geography (business_locations); this adds the severity side — a curated venue_severity reference seeded from FREE public sources (ATRA Judicial Hellholes, US Chamber ILR, nuclear-verdict reporting) — joined to client locations and surfaced in the submission packet + risk profile.',
    whatsNew: [
      'New venue_severity reference (state + county → tier severe/high/elevated/moderate/low), seeded ~24 rows incl. county overrides (Cook, Philadelphia, LA, Harris, Fulton, Orleans, St. Louis City, Madison, Midland, Bronx).',
      'Risk Profile page: a "Venue exposure" card — worst tier + per-location severity, source-labeled (directional flag, not a price).',
      'Broker submission packet PDF gains a "Venue Exposure" section (tenant uses full locations; off-platform Broker Pro uses primary-state baseline).',
      'Exposure not posture: deliberately NOT folded into the composite risk index (you can’t move out of a hellhole) — surfaced as its own dimension.',
    ],
    howToUse: [
      'Company → Risk Profile: the Venue exposure card sits alongside the readiness + composite cards.',
      'Broker → generate a client submission PDF: the Venue Exposure section lists each location’s venue severity.',
      'Refresh annually from the same free reports by editing the venue_severity table (or via a future web-grounded refresh agent).',
    ],
    setup: [
      'Migration venuesev01 (table + curated seed) — applied to dev; run ./scripts/migrate-prod.sh before prod deploy. No new feature flag (rides risk_profile + broker submission). Deploy backend + client build.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'wc-rates-viewer',
    date: '2026-06-21',
    category: 'Admin',
    title: 'WC rate data — by-state viewer + real CA/NY rates',
    summary:
      'The admin WC Rate Data page now shows what is actually loaded: a by-state table of loss-cost trends (Δ%, trend, effective date, source) + a class-code base-rate table, with a state/code filter and color-coded provenance (demo seed vs real filing). Seeded the first real figures — CA +8.7% (WCIRB 9/1/2025) and NY -4.4% (NYCIRB 10/1/2025).',
    whatsNew: [
      'Admin → WC Rate Data: "Rates by state" table (state, Δ loss cost, trend, effective date, source, note) + class-code base-rate table; filter by state or class code.',
      'Source coloring: demo/seed rows render amber, real filings emerald — at-a-glance provenance across all loaded states.',
      'Real free data seeded for CA (WCIRB +8.7%, eff 9/1/2025) and NY (NYCIRB -4.4%, eff 10/1/2025), replacing the demo placeholders. CA/NY are independent rating bureaus, not NCCI.',
    ],
    howToUse: [
      'Admin → WC Rate Data: the viewer tables sit above the CSV importers. Type a state code to filter both tables.',
    ],
    setup: [
      'CA/NY real rates already applied to RDS + dev (server/scripts/seed_wc_state_rates_real.sql). New GET endpoints /admin/wc-rates/state-rates + /class-codes — deploy backend + client build.',
    ],
    tag: 'new',
  },
  {
    id: 'submission-readiness-score',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Submission-readiness score — the data→price proof loop',
    summary:
      'A completeness score on the Risk Profile portal: "your WC + EPL data is X% underwriter-ready — finish these N items → tighter terms." Distinct from the risk index (how good the risk is); this measures how well-articulated the data is, the report\'s core causal claim that clean data wins better pricing. Ties HRIS/incident data → submission packet → risk index into one loop.',
    whatsNew: [
      'Risk Profile page gains a "Submission readiness" card: a 0–100 completeness score + a 10-item checklist (operating locations, headcount, industry, experience mod, claim classification, return-to-work, class codes, EPL questionnaire, anti-harassment policy, verified controls), each missing item showing the exact fix.',
      'Reuses the same inputs the submission packet is built from — no new data entry, no new feature flag (rides the existing risk_profile portal).',
      'The broker submission packet PDF now carries a "Submission readiness: X%" pre-flight banner listing what to complete before going to market.',
    ],
    howToUse: [
      'Company → Risk Profile (risk_profile feature): the Submission readiness card sits under the risk-index hero. Each unchecked item links to the work that completes it.',
      'Broker → generate a client submission PDF: the readiness banner appears at the top.',
    ],
    setup: [
      'None — no migration, no new flag. Deploy backend + client build.',
    ],
    tag: 'new',
  },
  {
    id: 'controls-evidence-and-claims-readiness',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Proof of Controls packet + Claims-readiness defense files',
    summary:
      'Two underwriter-facing artifacts built from data Matcha already holds (WTW "Insurance Marketplace Realities 2026" thesis: clean, documented risk wins better terms). (1) A universal "Proof of Controls" register that auto-compiles 8 risk controls and exports a packet — generalizing the healthcare resident-care asset to any employer. (2) A per-incident / per-ER-case "Claims-readiness" defense file (timeline + witnesses + investigation docs + policy-violation map + corrective actions).',
    whatsNew: [
      'Proof of Controls (new feature `controls_evidence`): 8 controls auto-derived — anti-harassment policy+signatures, training, discipline, ER cases, multi-state wage-hour (reusing the EPL-readiness engine), plus IR/OSHA incident response, credentialing currency, and safety programs.',
      'Each control can be verified/annotated (status override + note); export a single "Proof-of-Controls" PDF. The broker submission PDF now also carries a Risk Controls section.',
      'Claims-readiness packets (no new flag — rides Incidents + ER): a defensible PDF per IR incident and per ER case, repackaging existing timeline/witness/document/policy-mapping/corrective-action data.',
      'Broker surface: new Controls + Defense Files tabs on the client detail page, plus the controls section folded into the carrier submission packet.',
    ],
    howToUse: [
      'Company → Compliance → Proof of Controls (when `controls_evidence` is enabled): review the auto-filled controls, mark any verified with a note, then "Proof-of-Controls packet" to download.',
      'Company → an IR incident or ER case → the export panel now has a "Claims-readiness packet" download.',
      'Broker → a client → Controls tab (register + packet) and Defense Files tab (per-incident / per-case PDFs).',
    ],
    setup: [
      'Migration `ctrlev01` (table `company_control_evidence`) — applied to dev; run `./scripts/migrate-prod.sh` before prod deploy.',
      'Toggle the `controls_evidence` feature per company in Admin → Features (the claims-readiness packets need no flag).',
      'Deploy backend + client build.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'broker-portal-redesign',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Broker portal redesign — unified risk panel + tabbed hubs',
    summary:
      'A design pass on the broker portal: the Book of Business loses the five stacked stat-strips for one dense "Risk Posture" panel, the composite Risk Index becomes a headline KPI, and the six Administration nav rows fold into two tabbed hubs (Clients + Account). No data or behavior changed — same numbers, far less bulk.',
    whatsNew: [
      'Book of Business: the four near-identical band strips (WC posture, claim depth, EPL, Risk Index) collapse into one Risk Posture panel — each lens is a best→worst distribution bar with inline counts, WC claim-depth as a chip footer.',
      'Composite Risk Index promoted to a hero KPI alongside Total Clients / Employees / At-Risk; flat KPI tiles replace the watermark-icon stat cards.',
      'Nav: Onboarding · Pipeline · Seats · Referrals now live under a single Clients hub (tabs), and Team · Settings under an Account hub — sidebar drops from 9 rows to 5.',
      'Forms on Seats / Referrals / Team / Settings get consistent panel header bands, finished inputs, and emerald CTAs; both broker light and dark themes intact.',
    ],
    howToUse: [
      'Broker → Book of Business: the new KPI row + Risk Posture panel sit above the Accounts table.',
      'Broker → Clients and Broker → Account: switch sub-pages with the tab bar. Old bookmarks (/broker/seats, /broker/pipeline, /broker/referrals, /broker/team, /broker/settings) auto-redirect to the matching tab.',
    ],
    setup: [
      'None — frontend only, no migration or env change (commit 7e11dce). Deploy the client build.',
    ],
    tag: 'new',
  },
  {
    id: 'broker-theme-alerts',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Risk-theme alerts + broker suggestions (Action Center)',
    summary:
      'The Action Center Alerts tab now surfaces the qualitative incident themes from each client’s "Themes & People" analysis — e.g. "catastrophic forklift maintenance failures at Sherman Oaks" — each with a prescriptive, broker-voiced suggestion, alongside the existing TRIR/DART/lost-day trend alerts.',
    whatsNew: [
      'Theme alerts: high/critical incident hotspots per client (location-attributed) pulled from the IR risk-insights themes over the trailing 90 days.',
      'Each carries an AI broker-voiced "Suggested:" action (e.g. "Offer materials for retraining staff on proper high-density storage procedures").',
      'Shown with a ✨ Risk theme tag next to the quantitative trend alerts; deduped, severity-mapped, and auto-resolved when a theme stops recurring.',
    ],
    howToUse: [
      'Broker → Action Center → Alerts. Theme alerts generate when the tab opens (a brief "Scanning risk themes…") and appear with their suggested broker action.',
    ],
    setup: [
      'No migration (reuses broker_risk_alerts + its metadata jsonb). Themes derive from each client’s incident data; generation runs in FastAPI (the alert worker is pool-free) and reuses the 24h risk-insights cache.',
    ],
    tag: 'new',
  },
  {
    id: 'agentic-derive-upgrades',
    date: '2026-06-21',
    category: 'Broker',
    title: 'Agentic upgrades — derive from data instead of manual entry',
    summary:
      'The newer broker/compliance features now pull from existing data + AI, matching the rest of the platform, instead of starting empty and hand-typed. Four additions: WC class-code auto-map from employees, pay-equity analysis from payroll, AI scan-&-suggest on the registers, and a risk-profile AI narrative. Manual entry stays as a fallback everywhere.',
    whatsNew: [
      'WC class-codes: "Auto-map from employees" — Gemini maps job titles → NCCI classes and aggregates headcount + payroll; broker reviews + saves.',
      'Pay-equity: "Run analysis from payroll" — computes within-role pay dispersion from employee pay_rate (flags roles with excess spread) and logs it as the study that flips the EPL factor on real data. (Protected-class gap still needs HRIS demographics — noted in the result.)',
      'AI scan & suggest on the AI-hiring-tool, biometric, and resident-care safety-program registers — Gemini proposes starter rows from your industry/roles/incidents; review checkboxes → add selected.',
      'Risk Profile: "Explain my risk" — AI narrative of why your index is what it is + a prioritized action plan to improve insurance terms (client + broker views).',
    ],
    howToUse: [
      'Broker → client → Workers’ Comp tab → "Auto-map from employees".',
      'Company → Workforce Compliance → "Run analysis from payroll" (pay-equity) and "AI suggest" on the AI-audit / biometric registers.',
      'Company → Resident-Care Risk → "AI suggest" on safety programs; Compliance → Risk Profile → "Explain my risk".',
    ],
    setup: [
      'No migrations (reuses existing tables). Needs employee data (job_title, pay_rate) for the WC/pay-equity auto paths. Dev: seed_demo_employee_roles.sql gives a demo client realistic roles.',
    ],
    tag: 'new',
  },
  {
    id: 'broker-offplatform-automation',
    date: '2026-06-20',
    category: 'Broker',
    title: 'Off-platform automation — loss-run PDF parse + client-intake link',
    summary:
      'Removes the data-entry tax for off-platform (Broker Pro) clients. Upload a carrier loss-run PDF and Gemini extracts the WC figures into a draft to review; or send the prospect a shareable link to self-complete the EPL questionnaire — no account. Both feed the same WC + EPL + risk-index engines.',
    whatsNew: [
      'Loss-run PDF auto-parse: "Parse loss-run PDF" on an external client → Gemini reads the PDF → prefills the WC editor for review (never auto-saves; low-confidence parses flag a warning).',
      'Client-intake link: "Generate intake link" → shareable public URL; the prospect rates the 10 EPL factors in ~2 min; answers save (attributed to the broker) and rescore automatically. Link locks once completed or after 14 days.',
      'API: POST /broker/external-clients/{id}/loss-run (PDF) + /intake-link; public GET/POST /external-intake/{token}.',
    ],
    howToUse: [
      'Broker → External Book → a client → "Parse loss-run PDF" (upload the carrier PDF) → review the prefilled fields → Save.',
      'Or click "Generate intake link" → copy → send to the prospect; their answers populate the EPL score when they submit.',
    ],
    setup: [
      'DB: migration extintake01 (broker_external_intake_tokens) applied on dev; prod via ./scripts/migrate-prod.sh.',
      'Requires the Broker Pro plan (brokers.plan=\'pro\') — same gate as the rest of the External Book.',
    ],
    tag: 'new',
  },
  {
    id: 'wc-rate-feed-import',
    date: '2026-06-20',
    category: 'Broker',
    title: 'WC rate data — admin NCCI/state-bureau CSV import',
    summary:
      'Admin pipeline to load a licensed NCCI or public state-bureau WC rate feed via CSV, replacing the illustrative demo seed the broker Workers’-Comp surfaces read. The rate data is licensed/external (not buildable) — this is the ingestion that consumes it. Real public 2026 state loss-cost filings are pre-loaded for the demo book.',
    whatsNew: [
      'New Admin → Compliance Data → "WC Rate Data" page: upload state loss-cost CSV + class-code CSV, with templates, per-source row counts (seed vs import), and per-row error reporting.',
      'Idempotent upsert (state+effective-date / state+class-code), source-labeled so public + licensed rows coexist.',
      'Pre-loaded real public 2026 filings for 10 states (CA, IL, NV, FL, CT, NH, WV, GA, TN + national) via server/scripts/seed_wc_state_rates_public.sql.',
      'API: /admin/wc-rates/state-rates, /class-codes (CSV), /summary, /template/{kind}.',
    ],
    howToUse: [
      'Admin → WC Rate Data → download a CSV template → fill from a purchased NCCI feed or a public state filing → upload.',
      'The broker WC tab + NCCI overlay immediately read the imported rates (latest effective date per state wins).',
    ],
    setup: [
      'No migration (reuses wc_state_rates / wc_class_codes). Licensed NCCI manual data must be purchased + uploaded; public state loss-cost % filings are free to load.',
    ],
    tag: 'new',
  },
  {
    id: 'pay-equity-tracker',
    date: '2026-06-20',
    category: 'Compliance',
    title: 'Pay-equity study register (Workforce Compliance)',
    summary:
      'Fourth Workforce Compliance tracker: log each pay-equity audit + remediation with an annual cadence. A current study flips the broker EPL pay_equity factor from attested → derived — same pattern as the AI-audit register.',
    whatsNew: [
      'New "Pay-equity studies" section on the Workforce Compliance page — log study date, scope, adjusted gap %, and remediation; overdue flags by cadence.',
      'Feeds EPL: a current study (within cadence, gap remediated) scores high; overdue scores low; none falls back to the broker attestation.',
      'API: /workforce-compliance/pay-equity (CRUD); summary now includes pay_equity counts.',
    ],
    howToUse: [
      'Admin → Business Features → turn on "Workforce Compliance" for the company.',
      'That company → Workforce Compliance → "Pay-equity studies" → log study date, scope, adjusted gap %, and remediation.',
      'A current study (within cadence, gap remediated) auto-flips the broker EPL pay_equity factor from attested → derived.',
    ],
    setup: [
      'DB: migration payequity01 (pay_equity_reviews) applied on dev; prod via ./scripts/migrate-prod.sh.',
    ],
    tag: 'new',
  },
  {
    id: 'resident-care-risk',
    date: '2026-06-20',
    category: 'Compliance',
    title: 'Resident-Care Risk asset (healthcare / senior-living)',
    summary:
      'Packages the controls underwriters value in healthcare/senior-living (WTW p.175–176) into a documented program + insurer-facing PDF: safety-program register, MVR reviews (hire + annual), and credentialing currency (from existing employee_credentials). Gated by the new resident_care flag.',
    whatsNew: [
      'New "Resident-Care Risk" page (Safety group): safety-program register, MVR-review register with overdue flags, credentialing-currency readout, and summary strip.',
      'One-click insurer asset PDF — a "resident-care risk management program" leave-behind to present alongside the loss run.',
      'API: /resident-care/summary, /programs (CRUD), /mvr (CRUD), /asset.pdf.',
    ],
    howToUse: [
      'Admin → Business Features → turn on "Resident-Care Risk" for a healthcare/senior-living company.',
      'That company → Safety → Resident-Care Risk → log safety programs + MVR reviews → "Insurer asset" to download the PDF.',
    ],
    setup: [
      'DB: migration rescare01 (safety_programs, mvr_reviews) applied on dev; prod via ./scripts/migrate-prod.sh.',
    ],
    tag: 'new',
  },
  {
    id: 'wc-class-codes',
    date: '2026-06-20',
    category: 'Broker',
    title: 'Workers’-Comp class-code exposures',
    summary:
      'Class-level WC underwriting (WTW p.32–33). Brokers can record a client’s payroll/headcount by NCCI class code; each class is matched to a reference rate and an estimated manual premium (payroll ÷ 100 × rate) is shown. Reference rates are an illustrative seed pending a licensed NCCI feed.',
    whatsNew: [
      'New "Class-code exposures" section on the broker client Workers’ Comp tab — add/remove payroll by NCCI class, with per-class and total estimated manual premium.',
      'Reference class codes seeded (clerical, carpentry, masonry, trucking, home-health, hospital, restaurant, retail, …) flagged source="seed (demo)".',
      'API: GET /broker/wc-class-codes, GET/POST/DELETE /broker/wc-portfolio/{id}/class-exposures.',
    ],
    howToUse: [
      'Broker → a client → Workers’ Comp tab → "Class-code exposures".',
      'Add payroll/headcount by NCCI class code; per-class and total estimated manual premium (payroll ÷ 100 × rate) show automatically.',
    ],
    setup: [
      'DB: migration wcclass01 (wc_class_codes, company_wc_class_exposures) applied on dev; prod via ./scripts/migrate-prod.sh.',
      'Replace the seeded reference rates with a licensed NCCI/state-bureau feed when available.',
    ],
    tag: 'new',
  },
  {
    id: 'composite-risk-index',
    date: '2026-06-20',
    category: 'Broker',
    title: 'Composite risk index + client-facing risk portal',
    summary:
      'One 0–100 risk index per client (workers’-comp + EPL + compliance, weighted roll-up of scores already computed — no new data). The report’s "Risk Index Model" / "Risk Intelligence Central". Brokers see it as one benchmarkable number per client; businesses see their own via a new client-facing Risk Profile portal.',
    whatsNew: [
      'Broker dashboard: new "Risk index" strip (avg + Strong→Exposed distribution across the book).',
      'Broker API: GET /broker/risk-index (rollup) + /broker/risk-index/{id} (per client with component breakdown).',
      'Client-facing "Risk Profile" page (gated by the new risk_profile flag): the business’s own index, the 3 component bars, and a "how to improve your terms" fix list.',
      'Index = WC (wt 40, from severity band + experience mod) + EPL readiness (wt 35) + compliance coverage (wt 25); components with no data drop out and weights renormalize.',
      'Also scores off-platform (Broker Pro) clients (WC + EPL only) — a "Risk" column on the External Book + an index chip on each external client.',
    ],
    howToUse: [
      'Broker: open the dashboard — the Risk index strip sits under EPL readiness.',
      'Client portal: Admin → Business Features → turn on "Risk Profile" for a company → that company sees Compliance → Risk Profile.',
    ],
    tag: 'new',
  },
  {
    id: 'workforce-compliance',
    date: '2026-06-20',
    category: 'Compliance',
    title: 'Workforce Compliance — pay transparency · AI-audit · biometric (also feeds broker EPL)',
    summary:
      'New business-facing feature tracking three employment-practices compliance obligations: per-state pay-transparency posting compliance, an AI hiring-tool bias-audit register, and a biometric/BIPA consent inventory. Each is a legal obligation the business must meet anyway (so it’s genuinely useful to the tenant), and — for companies served by a broker — it flips the matching broker EPL-readiness factors from broker-attested to data-derived automatically.',
    whatsNew: [
      'New "Workforce Compliance" page under the Compliance group with 3 sections.',
      'Pay transparency: lists the states in the company’s footprint that require salary ranges in postings; mark each compliant.',
      'AI hiring-tool audits: register each automated hiring tool + its last bias-audit date; overdue flags by cadence (NYC LL144 / IL / CO require regular audits).',
      'Biometric/BIPA consent: inventory each collection point (time clocks, access control) + whether written consent is on file ($1–5k statutory damages per violation).',
      'Broker tie-in: when a client has this on, the broker’s EPL detail shows pay-transparency / AI-audit / biometric factors as "derived" (from the real data) instead of broker yes/no, and the derived/attested split shifts accordingly.',
    ],
    howToUse: [
      'Admin → Business Features → turn on "Workforce Compliance" for a company.',
      'That company → Compliance → Workforce Compliance → set pay-transparency states, register AI tools, log biometric points.',
    ],
    setup: [
      'DB: migration wfcomp01 (hiring_ai_audits, biometric_consent_points, pay_transparency_status) is applied on dev; apply to prod with ./scripts/migrate-prod.sh.',
      'Pay-transparency states are a built-in static list (CA, CO, WA, NY, IL, …) — extend in services/workforce_compliance.py as laws change.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'broker-submission-packet',
    date: '2026-06-20',
    category: 'Broker',
    title: 'Carrier submission packet + AI coverage-gap (+ 50-state WC rates)',
    summary:
      'The "outward" layer the WTW report calls the terms-winning move: brokers can generate a carrier-ready underwriting submission PDF from a client’s Workers’-Comp + EPL posture, plus an AI coverage-gap read of where the client may be under-protected. Works for both on-platform clients and off-platform Broker-Pro clients. Also backfilled headline WC rate trends for all 50 states so the rate overlay is no longer blank outside the report’s named states.',
    whatsNew: [
      'New "Submission" tab on the client detail (and a "Carrier submission" card on external clients): one-click branded PDF with the client’s WC metrics (TRIR/DART/experience-mod/claim-mix/state trend) + the EPL readiness breakdown + a loss-mitigation narrative.',
      '"Coverage-gap analysis": Gemini reads the client’s posture (plus any current coverage the broker enters) and flags likely gaps — e.g. EPL limit light for the headcount/claim profile, or no cyber despite employee PII — with concrete pre-renewal actions. Best-effort; the PDF renders regardless.',
      'WC state-rate overlay now covers all 50 states + DC. The states beyond the report’s filing table are headline estimates, clearly flagged "pending licensed feed".',
    ],
    howToUse: [
      'Broker → open a client → "Submission" tab (on-platform) or scroll to "Carrier submission" (off-platform).',
      'Click "Download submission PDF" for the carrier-ready packet, and/or "Coverage-gap analysis" for the AI read.',
    ],
    setup: [
      'DB: migration wcstates01 (50-state WC rate seed) is applied on dev; apply to prod with ./scripts/migrate-prod.sh.',
      'Coverage-gap uses the existing Gemini key (LIVE_API / GEMINI_API_KEY) — if unset, the button degrades gracefully and the PDF still works.',
      'Replace the headline state estimates with a licensed NCCI / state-bureau feed when one is contracted (data task, not code).',
    ],
    tag: 'action-needed',
  },
  {
    id: 'broker-pro-off-platform',
    date: '2026-06-20',
    category: 'Broker',
    title: 'Broker Pro — score off-platform clients (not on Matcha)',
    summary:
      'Brokers can now manage clients who aren’t Matcha tenants. Flip a broker to the new "Broker Pro" plan in admin and they get an "External Book": add a non-tenant client, key in their carrier loss-run summary + an EPL questionnaire, and get the same Workers’ Comp + EPL readiness scores as on-platform clients. This turns the scoring engine from a pass-through add-on into a standalone broker tool for the whole book.',
    whatsNew: [
      'New per-broker "Broker Pro" entitlement (lives on the broker, not a company feature flag) — toggle it in Admin → Brokers → edit → Plan.',
      'Pro brokers get an "External Book" sidebar entry; add off-platform clients (name, industry, headcount, state).',
      'Per client, enter the carrier loss-run summary (recordables, DART, lost days, cumulative-trauma/acute, post-termination, return-to-work, experience mod, premium) → WC TRIR/DART/severity/EMR + the NCCI state-rate overlay compute automatically.',
      'EPL: the broker grades all 10 underwriting factors from the questionnaire → a 0–100 readiness score + band.',
      'Off-platform scores use the exact same weights/bands as on-platform clients, so they’re directly comparable across the book.',
      'Standard brokers are unaffected — they never see the section until upgraded.',
    ],
    howToUse: [
      'Admin → Brokers → edit a broker → set Plan = "Pro".',
      'That broker logs in → "External Book" → "Add client".',
      'Open the client → "Enter loss run" (key the carrier figures) and set each EPL factor from the underwriting questionnaire. Scores update live.',
    ],
    setup: [
      'DB: migration brokerpro01 (brokers.plan + broker_external_clients / _wc / _epl_attestations) is applied on dev; apply to prod with ./scripts/migrate-prod.sh.',
      'v1 is broker-keyed. Loss-run PDF auto-parse + a client-fills-it intake link are the planned v2.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'broker-epl-readiness',
    date: '2026-06-20',
    category: 'Broker',
    title: 'EPL Readiness — score a client’s HR posture against what EPL underwriters ask',
    summary:
      'Brokers get an Employment Practices Liability (EPL) underwriting-readiness score per client, built from the HR data Matcha already holds plus a short broker-attested checklist. It maps the client’s posture to what EPL carriers actually ask about (WTW Insurance Marketplace Realities 2026), so the broker has a consultative talking point and a punch-list to fix before renewal. Lives on a new client-detail tab + a book-wide strip on the broker dashboard.',
    whatsNew: [
      'Composite 0–100 readiness score per client with a band (Strong / Adequate / Developing / Exposed) and a headline “top gap”.',
      'Derived automatically from existing data (55% of the score): anti-harassment/EEO policy + signature rate, anti-harassment training completion, documented progressive discipline, ER case management, and multi-state wage & hour compliance coverage.',
      'Broker-attested checklist (45%): the five underwriting asks Matcha has no data source for — pay-transparency compliance, biometric/BIPA controls, pay equity, AI hiring-tool bias audit, and DEI posture. Mark each In place / Partial / Gap during a client review and the score updates live.',
      'Broker dashboard gains an EPL band-distribution strip (average score + Strong/Adequate/Developing/Exposed counts) across the whole book.',
    ],
    howToUse: [
      'Broker → Book of Business → open a client → “EPL Readiness” tab.',
      'Read the derived factors (filled in automatically from that client’s Matcha data), then set the attested items as you confirm them with the client.',
      'Use the score + top-gap as the consultative pitch — what to shore up before the EPL renewal.',
    ],
    setup: [
      'DB: migration epldeep01 (company_epl_attestations) is applied on dev; apply to prod with ./scripts/migrate-prod.sh.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'broker-wc-depth',
    date: '2026-06-20',
    category: 'Broker',
    title: 'Workers’ Comp depth — experience mod, claim taxonomy, NCCI rates, return-to-work',
    summary:
      'The broker Workers’ Comp view goes deeper to match how carriers actually underwrite WC: an experience-mod (EMR) trajectory, cumulative-trauma vs acute + post-termination claim tracking, per-state NCCI rate trends, and return-to-work metrics. HR classifies each recordable on the incident screen; the broker sees the rolled-up analytics. (WTW Insurance Marketplace Realities 2026.)',
    whatsNew: [
      'New “Workers’ Comp” tab on the broker client detail: TRIR/DART header, claim mix (cumulative trauma vs acute), post-termination count, return-to-work (open vs resolved + avg days), NCCI rate trend per operating state, and an experience-mod trajectory.',
      'Experience mod (EMR) entry: record each policy period’s mod (+ carrier/premium) — debit/credit coloring; it’s the single number carriers price WC on.',
      'NCCI per-state loss-cost trends seeded from the 2026 filings (e.g. NV +21.9%, MD −12.3%), auto-matched to each client’s business-location states.',
      'Incident screen: an OSHA-recordable incident now has a “WC Classification” control — claim type (acute / cumulative trauma), post-termination flag, return-to-work date — which feeds the broker analytics.',
      'Broker dashboard: a WC-depth strip (cumulative-trauma, post-termination, open lost-time, and clients operating in rate-increase states) across the book.',
    ],
    howToUse: [
      'HR/admin: open an OSHA-recordable incident → Overview → “WC Classification” → set claim type, post-termination, and return-to-work date.',
      'Broker → Book of Business → open a client → “Workers’ Comp” tab → review claim mix / RTW / state rate trend.',
      'On that tab, click “Record mod” to log the client’s experience mod each policy period and build the trajectory.',
    ],
    setup: [
      'DB: migration wcdeep01 (ir_incidents claim fields + wc_state_rates + company_wc_mods) is applied on dev; apply to prod with ./scripts/migrate-prod.sh.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'werk-ios-chat',
    date: '2026-06-19',
    category: 'Werk',
    title: 'Native iOS Werk app — chat (channels, DMs, calls) + push',
    summary:
      'A native iOS Werk client now exists, sharing the macOS app’s networking/model/chat core so it stays in lockstep. v1 is the full chat system: real-time channels, direct messages, and LiveKit audio calls / video broadcasts, with APNs push. To test it, flip a business to Werk Lite in Business Features and log into the iOS build as one of its users.',
    whatsNew: [
      'New iOS app target (WerkiOS) inside the existing Xcode project; reuses the same login, channels socket, models, and the channel chat view-model the macOS app uses (no second codebase to keep in sync).',
      'Channels: real-time chat with optimistic send, reactions, replies, edit/delete, typing indicators, presence, and photo attachments.',
      'Direct messages: inbox + thread + start-new-conversation (people search).',
      'Calls & broadcast: join an audio call or watch a live video broadcast from the phone; join is open to channel members, starting one is Pro-gated (same as macOS).',
      'Push (APNs): the phone gets notified of new channel messages, DMs, mentions, and call invites — only when you don’t have the app open (so it never double-buzzes while you’re active on desktop). Tapping a push deep-links to the channel/DM.',
      'Admin: "Werk Lite" is now a per-company toggle in Business Features (previously only set by signup), so you can switch an existing business on for testing.',
    ],
    howToUse: [
      'Admin → Business Features → find the company → turn ON "Werk Lite" AND "Matcha Work" (Werk Lite needs both). Optionally turn on "Werk Lite — any member can start calls".',
      'Build the WerkiOS scheme in Xcode (desktop/Werk/Matcha.xcodeproj) onto a simulator or device.',
      'Log into the app as a business admin or employee of that company — channels and DMs work immediately.',
    ],
    setup: [
      'DB: migration devicetok01 (device_tokens) is applied on dev; apply to prod with ./scripts/migrate-prod.sh (now uses `alembic upgrade heads`).',
      'Push (optional — chat works without it): `pip install aioapns` in the server venv and set APNS_KEY_ID / APNS_TEAM_ID / APNS_AUTH_KEY_PATH / APNS_BUNDLE_ID (com.matchawork.app) / APNS_USE_SANDBOX. Unset → push is a silent no-op.',
      'Real-device push also needs the iOS Push Notifications capability + a signing team on the WerkiOS target. Simulator builds and in-app realtime work without it.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'cappe-freeform-canvas',
    date: '2026-06-19',
    category: 'Cappe',
    title: 'Freeform canvas — click & place individual elements',
    summary:
      'Pro/Business can edit individual elements freely: start from a template and hit "Customize freely" to turn any Hero/CTA/Split/Text section into a draggable freeform layout, or add a "Blank / Freeform" section from scratch. Click any heading, text, image, or button and drag it on a snap-grid — separate desktop & mobile layouts. Squarespace "Fluid Engine"–style.',
    whatsNew: [
      '"Customize freely" on a Hero/CTA/Split/Text section → converts it (keeping its content) into a freeform layout where every piece — heading, subheader, buttons, image — is individually editable. (One-way.)',
      'Or add a "Blank / Freeform" section and drop in heading / text / image / button elements.',
      'Click an element to select it; drag to move (snaps to a grid), drag a corner to resize, double-click text/buttons to retype.',
      'Per-element styling: font/size/weight/spacing/color/align for text; fit/radius for images; label/link/variant/colors/radius for buttons.',
      'Separate Desktop and Mobile layouts — flip the toggle to arrange the phone view independently (auto-stacks until you customize it).',
      'Published pages stay fast: positions render as plain CSS grid (no editor code shipped), so it scales to many sites.',
    ],
    howToUse: [
      'Open a site → a page → the editor opens in Canvas mode (Pro/Business).',
      'On an existing section: select it → "✨ Customize freely" → its content becomes editable elements.',
      'Or Add block → "Blank / Freeform" to build from scratch.',
      'Click an element to edit it in the floating panel; drag to move, corner-drag to resize. Use the Desktop / Mobile toggle to tune each breakpoint, then Save.',
    ],
    tag: 'new',
  },
  {
    id: 'cappe-staff-csv-import',
    date: '2026-06-19',
    category: 'Cappe',
    title: 'Staff CSV import with branch auto-mapping',
    summary:
      'Multi-location businesses can import their team from a CSV. A branch column maps each employee to the right location automatically — no manual re-tagging.',
    whatsNew: [
      'Import staff from a CSV (name required; optional branch, bio, active).',
      'The branch column is matched to a location by name, so each employee auto-lands at their branch; blank = works at all locations.',
      'Re-importing the same name updates that person (branch/bio) instead of creating a duplicate; unknown branch names are reported per-row.',
      'Single-location sites get a simpler template with no branch column.',
    ],
    howToUse: [
      'Open a site → Bookings → Staff → Import CSV.',
      'Download the template (multi-location templates are pre-filled with your real branch names).',
      'Fill in your team, upload, and review the per-row summary (added / updated / branch-mapped / skipped).',
    ],
    tag: 'new',
  },
  {
    id: 'cappe-domains',
    date: '2026-06-18',
    category: 'Cappe',
    title: 'Domain buying, connecting & management',
    summary:
      "Tenants can buy a domain through Cappe (we register it via Porkbun and resell at wholesale + a flat markup), or connect one they already own. Includes an in-app DNS editor, auto-renew, and transfer-out.",
    whatsNew: [
      'Search + buy a domain in the site editor — paid via Stripe on our platform account (we keep the margin).',
      'Connect a domain you already own, verified by a DNS TXT record before it goes live (prevents domain hijacking).',
      'In-app DNS records editor (A / CNAME / MX / TXT…) for domains bought through us.',
      'Auto-renew: the card is saved at purchase; a cron charges the tenant before expiry and only then renews — you never pre-pay for a non-payer.',
      'Transfer-out request flow with the 60-day ICANN lock enforced.',
    ],
    howToUse: [
      'Open a site → Settings → Custom domain.',
      "Type a name to search, pick an available one, and click Buy — the tenant completes Stripe checkout and the domain auto-registers + points at the site.",
      "Or paste a domain they own under “Connect it”, add the shown TXT record at their registrar, and click Verify.",
      'On an active bought domain: use DNS to manage records, toggle Auto-renew, or request Transfer out.',
    ],
    setup: [
      'Apply migrations zzzzcappe19 + zzzzcappe20 (dev → prod).',
      'Fund a Porkbun account, enable API, set PORKBUN_API_KEY / PORKBUN_SECRET_KEY + CAPPE_DOMAIN_MARKUP_CENTS.',
      'Add a Stripe PLATFORM webhook → /api/cappe/domains/webhook, set CAPPE_PLATFORM_WEBHOOK_SECRET.',
      'Stand up Caddy on-demand TLS gated by /api/cappe/tls/authorize (custom domains need their own certs).',
      "Enable the renewal cron: scheduler_settings row task_key='cappe_domain_renewals'.",
      'Full detail in server/app/cappe/DOMAINS.md.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'cappe-storefront',
    date: '2026-06-16',
    category: 'Cappe',
    title: 'Storefront payments, receipts & inventory',
    summary:
      'Each business connects its own Stripe account to take card payments on its Cappe storefront (we take a 2% platform fee). Plus branded receipts and per-variant inventory.',
    whatsNew: [
      'Stripe Connect: customers pay the business directly; a 2% fee routes to the platform.',
      'Receipts: numbered, tax-aware, branded PDF emailed to the customer + downloadable by the owner.',
      'Inventory: per-variant stock, low-stock alerts, manual adjustments with an audit log.',
    ],
    howToUse: [
      'Site → Orders → connect the business Stripe account (one-time onboarding).',
      'Set tax rate + receipt prefix in Shop settings.',
      'Add stock numbers / low-stock thresholds per product or variant; use Adjust to restock or correct.',
    ],
    tag: 'new',
  },
  {
    id: 'cappe-setup-wizard',
    date: '2026-06-15',
    category: 'Cappe',
    title: 'Guided setup wizard + canvas editor for Pro',
    summary:
      'New signups get a short setup wizard (single vs. multi-location), and the free-form canvas editor is now unlocked for Pro.',
    whatsNew: [
      'Post-signup wizard: pick one location or several — shapes CSV imports, bookings, and services.',
      'Canvas (free-form drag editor) is now available on Pro, not just Business.',
    ],
    howToUse: [
      'New tenants land on the wizard automatically on first sign-in.',
      'Pro tenants: open a page → toggle to Canvas mode to drag blocks freely.',
    ],
    tag: 'new',
  },
]
