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
  tag?: AdminUpdateTag
}

export const ADMIN_UPDATES: AdminUpdate[] = [
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
