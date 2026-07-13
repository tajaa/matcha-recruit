-- /admin/updates changelog rows for everything shipped 2026-07-08 → 2026-07-13
-- (last update entry before this batch was analysis-pilot, 2026-07-07).
-- Idempotent: deletes each id first, shifts positions, inserts at top in
-- reverse-chronological order (newest = position 0).
-- Run against dev AND prod.

BEGIN;

DELETE FROM admin_updates WHERE id IN (
  'hr-pilot-launch',
  'employee-scheduling',
  'newsletter-block-builder',
  'broker-pilot-templates',
  'scope-registry-compliance-library',
  'legal-pilot-hardening-pass',
  'limit-adequacy-risk-transfer',
  'handbook-pilot-sharing-viewer',
  'risk-analysis-depth-hardening'
);

UPDATE admin_updates SET position = position + 9;

INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) VALUES

(
  'hr-pilot-launch',
  0,
  '2026-07-13',
  'Matcha-work',
  'HR Pilot — matcha-work thread mode for on-site supervisors, with a hard-stop escalation gate',
  'A new matcha-work thread mode for supervisors who need HR guidance without corporate HR in the loop. Grounds answers in the company''s own handbook + active policies + per-state jurisdiction summary + the discipline ladder, but runs every message through a deterministic pre-AI gate first — harassment, safety, leave/medical, and termination/legal topics never reach the model, they get refused and routed to corporate HR.',
  '["New hr_pilot thread mode (registry-driven, like compliance/payer/legal/risk/training) grounded on handbook sections, active policies, a per-state jurisdiction summary, and the static discipline-ladder steps — same corpus handbook_pilot already reads.", "Deterministic escalation gate (services/hr_pilot_escalation.classify_message) runs BEFORE any AI call on every message. Harassment/discrimination, workplace safety, leave/medical, and termination/legal topics are refused outright and logged to mw_escalated_queries — the same review queue as low-confidence AI escalations.", "Admin toggle lives in the Matcha Work features group (moved there from AI Pilots — it''s a thread mode, not a standalone Pilot page)."]',
  '["Enable hr_pilot for the company, then toggle the HR Pilot mode on a matcha-work thread the same way you toggle Compliance/Legal/Risk/Training modes.", "A supervisor asking about a raise, a schedule swap, or a policy question gets grounded AI guidance. Anything touching harassment, safety, leave, or termination gets a refusal + auto-routes to corporate HR — no AI drafting on those topics, by design."]',
  '["Admin → Business Features → Matcha Work group → toggle \"HR Pilot\" per company (default off, not bundled)."]',
  '["The escalation gate is a hard stop, not an advisory — unlike the discipline compliance gate, there is no override path here because the point is keeping AI out of legally sensitive conversations entirely, not judging them."]',
  NULL
),

(
  'employee-scheduling',
  1,
  '2026-07-12',
  'Employee Scheduling',
  'Employee Scheduling — shift scheduling, templates, and swap/drop requests over the existing roster',
  'A new paid add-on: admins build and publish shifts against the existing employee roster, generate whole weeks from reusable shift templates, and employees see their published shifts and can request swaps, drops, or mark themselves unavailable for admin approval. Double-booking and overrun are guarded on every write path, not just create.',
  '["Admins build/publish shifts (date/time, role, location, break, required headcount), assign employees, and generate a week from a reusable shift template (time-of-day + weekday mask).", "Employees view published shifts and file swap / drop / unavailability requests through the employee portal; admins approve or deny.", "Double-booking is guarded on create, assign, swap-approval, AND retime — each conflict 409s with a forceable override; a headcount overrun 409s the same way.", "Cancelled shifts are terminal — can''t be flipped back to published once cancelled, so a resurrected shift can''t reappear on an assignee''s portal.", "Employees who''ve left (terminated/offboarded) are never schedulable, even if a stale assignment exists."]',
  '["Enable employee_schedule for the company. Admin → Employee Schedule: build shifts, or create a shift template once and generate weeks from it.", "Employees see their shifts on the portal Schedule tab and can request a swap/drop/unavailability there; admin approves from the same surface."]',
  '["Apply migration empsched01 (schedule_shifts / schedule_shift_assignments / schedule_shift_templates / schedule_requests / schedule_audit_log). Applied to DEV; PROD pending — run migrate-prod.sh.", "Admin-toggle the employee_schedule feature per company (paid add-on, not bundled)."]',
  NULL,
  'action-needed'
),

(
  'newsletter-block-builder',
  2,
  '2026-07-13',
  'Newsletter',
  'Newsletter — visual block builder + email-safe rendering, plus an idea scratchpad and template generator',
  'The newsletter tool moves from a plain text editor to a real "website-in-the-inbox" visual block builder — drag in image/text/button/divider blocks and get an email-safe render (table-based HTML, inlined styles) that survives Gmail/Outlook clipping. A scratchpad captures newsletter ideas before they''re ready to build, and a template generator scaffolds a starting layout with mandatory media so nobody ships a text-only blast by accident.',
  '["Visual block builder: image, text, button, divider, and layout blocks, drag-reordered, live preview.", "Form-mode ⇄ preview sync — edit in the structured form or the visual canvas and both stay in sync.", "Email-safe renderer: table-based layout + inlined CSS so the newsletter looks the same in Gmail/Outlook/Apple Mail as it does in the builder.", "Idea scratchpad for newsletter drafts that aren''t ready to build yet.", "Template generator requires at least one media block — prevents an all-text send that renders as a wall of text in the inbox."]',
  '["Company → Newsletter → new template or scratchpad idea → build with the visual block editor → preview → send.", "Use the template generator to start from a scaffolded layout instead of a blank canvas."]',
  NULL,
  NULL,
  NULL
),

(
  'broker-pilot-templates',
  3,
  '2026-07-12',
  'Broker Pilot',
  'Broker Pilot — starter templates (modes) + structured contract-review output',
  'Broker Pilot gains starter templates so a broker doesn''t face a blank chat — pick a mode (e.g. contract review, submission prep) and the assistant starts from a structured prompt. Contract review now returns structured output (not just prose) so findings can be displayed and acted on directly, matching the grounding pattern the rest of the Pilot family uses.',
  '["Starter template picker for Broker Pilot sessions — each template seeds a mode-specific opening prompt instead of a blank chat.", "Contract review mode returns structured findings (not free-form prose), consistent with how Limit Adequacy''s risk-transfer engine already classifies contract clauses.", "Grounds on the client''s own records the same way Legal/Handbook/Analysis Pilot do — cited, not guessed."]',
  '["Broker Pilot → New session → pick a starter template to seed the conversation instead of starting blank."]',
  NULL,
  NULL,
  NULL
),

(
  'scope-registry-compliance-library',
  4,
  '2026-07-11',
  'Compliance',
  'Scope Registry + Compliance Library — canonical business-category taxonomy drives what compliance data gets fetched, codified, and served',
  'A structural rework of how the compliance engine decides "what does this business need to comply with." A new scope registry maps a company (industry + jurisdiction + operational facts) to a canonical taxonomy of applicable legal obligations, replacing ad-hoc industry-keyword matching. Scope Studio (merged from the old separate Industry Reqs + Specialty Research admin pages) lets admins see what SHOULD be fetched for a scope, queue research against real authoritative sources (eCFR federal + curated CA), codify the results into the regulatory library with provenance, and read the underlying statute text in-app. Jurisdiction Data was renamed Compliance Library to match. A new baseline eval suite (enumerated federal + CA labor master-list) measures coverage against a known-complete list, not just internal consistency.',
  '["New scope_registry schema (migration scoperg01): canonical business-category taxonomy, classification, jurisdiction-chain inheritance, and a fetch queue — \"here''s what''s missing for this scope, go get it.\"", "Authority ingest from real sources: eCFR (federal) + a curated, individually-cited CA labor set, with citation verification before anything is stored.", "\"Research these\" in Scope Studio codifies the fetch queue directly — closes the loop from scope → fetch → store without leaving the panel.", "Codify layer stores full statute/regulation body text (not just a summary) with an in-app statute reader drawer; every codified obligation links back to its Compliance Library record and shows codify provenance.", "Anti-polymorphy fix: one obligation now maps to exactly one tag / one active row (previously the same legal requirement could get filed under multiple categories, double-counting coverage).", "Authority drift propagation: when a source goes dead or a statute is repealed, the drift is now propagated to every policy that cited it, with a review queue + dead-source-URL badges.", "Admin consolidation: Industry Reqs + Specialty Research pages retired into one Scope Studio page; \"Jurisdiction Data\" renamed \"Compliance Library.\"", "New baseline eval suite: an enumerated federal + CA labor master-list (not the sampled completeness suite) — a hard floor coverage check, surfaced in the Evals tab gap dashboard.", "Federal labor baseline now scope-codified directly, closing a gap where federal-level (non-state) requirements weren''t flowing through the registry."]',
  '["Admin → Compliance Library (renamed from Jurisdiction Data) → Scope Studio: browse scope, see the fetch queue, click \"Research these\" to codify, or open the statute reader on any codified obligation.", "Evals tab now shows a baseline-coverage banner (enumerated master-list) alongside the existing completeness/authority/tagging/golden suites."]',
  '["Apply migration scoperg01 (scope registry schema) before deploying — the registry is additive, existing jurisdiction_requirements reads are unaffected until scope-driven fetch queues are used.", "This is a multi-week engine change (see docs/ONE_COMPLIANCE_SYSTEM.md at repo root for how the three admin surfaces now connect, and the compliance coverage gap-analysis + implementation-blueprint docs for the roadmap)."]',
  NULL,
  'action-needed'
),

(
  'legal-pilot-hardening-pass',
  5,
  '2026-07-11',
  'Legal Pilot',
  'Legal Pilot — evidence scoped to the actual matter subject, not just location; case-law jurisdiction fix',
  'A hardening pass on Legal Pilot''s grounding: evidence retrieval and case-law search were pulling records/cases outside the actual matter subject (e.g. by location alone, or with generic vocabulary for clinical matters), which could surface irrelevant or out-of-jurisdiction material in an attorney-facing packet. Fixed to scope strictly to the matter''s real subject, including party names in case-law queries and a veto for matters whose subject the corpus doesn''t actually model.',
  '["Evidence + case-law research now scoped to the matter''s actual subject, not just its location — location alone was too broad.", "Case-law search includes party names in the query and no longer returns out-of-jurisdiction results.", "Clinical/healthcare matters use correct clinical subject vocabulary instead of generic terms.", "Unmodeled-subject veto: if the corpus doesn''t actually model what the matter is about, Legal Pilot says so instead of grounding on tangential records.", "Disabled-subsystem note now correctly says \"this data source is off,\" not \"these records don''t exist\" — the two read very differently to an attorney.", "Evidence sidebar rendering + scroll fixes."]',
  '["No workflow change — matters ground more precisely automatically. Worth re-reviewing any packet generated before this fix if the matter''s subject was narrow or clinical."]',
  NULL,
  NULL,
  NULL
),

(
  'limit-adequacy-risk-transfer',
  6,
  '2026-07-09',
  'Limit Adequacy',
  'Limit Adequacy — contract risk-transfer review: deterministic insurability verdicts on indemnity clauses',
  'Extends Limit Adequacy beyond "do you carry enough limit" into risk transfer: a deterministic engine reads each uploaded contract''s indemnification clause and returns an insurability verdict — likely void by statute, uninsurable exposure, insurable, or needs review — based on the indemnity form (broad/intermediate/limited) crossed with a curated, individually-cited table of state anti-indemnity statutes. Contracts now retain their source PDF (previously parsed and discarded) so clause findings stay verifiable, in their own S3 bucket.',
  '["New risk-transfer engine (services/risk_transfer.py): indemnity form × a curated per-state anti-indemnity statute table → likely_void_by_statute / uninsurable_exposure / insurable / review.", "Confirm-before-verdict: an unconfirmed AI extraction is always provisional and gated in Analysis Pilot''s needs_review queue — never a silent verdict.", "Unmapped state → review for the enforceability half only (the statute table is deliberately partial). Insurability under the CGL insured-contract grant is state-independent, so a broad-form clause is uninsurable_exposure even in an unmapped state — not a blanket \"review.\"", "PATCH is a true partial update keyed on which fields the caller actually sent — an explicit null clears a field, an unsent field is untouched, and confirmed_at only resets when a verdict input actually changes (a rename can''t silently un-confirm a contract).", "Source PDFs are now retained (storage_path) in their own S3 bucket (S3_CONTRACTS_BUCKET) instead of parsed-and-discarded — clause findings stay checkable against the source. Falls back to the shared bucket if unconfigured, never a 500.", "Broker Pilot now explains the risk-transfer feature to brokers reviewing a client''s contracts."]',
  '["Company → Limit Adequacy → Contracts: uploaded contracts now show a risk-transfer verdict per indemnity clause alongside the existing limit-adequacy diff.", "Broker → client → Limits tab: same verdicts, plus contract writes require the client''s own limit_adequacy flag so a contract can''t be stranded where the client can''t see it."]',
  '["Apply migration limadq02 (risk_transfer schema). Set S3_CONTRACTS_BUCKET in prod .env.backend or contract uploads silently land in the shared private bucket."]',
  '["Scope guard: insurance + risk-transfer provisions only — never payment/termination/IP/dispute terms. Every surface carries a not-legal-advice disclaimer."]',
  'action-needed'
),

(
  'handbook-pilot-sharing-viewer',
  7,
  '2026-07-09',
  'Handbook Pilot',
  'Handbooks — public share links + employee acknowledgement, plus an intelligent viewer with compliance provenance in Handbook Pilot',
  'Two additions to the handbook stack. First, handbooks can now be shared via a public link with employee acknowledgement tracking — no login required, the same pattern as the anonymous IR intake links. Second, Handbook Pilot''s drafting view gained an intelligent handbook viewer that shows compliance provenance inline — which jurisdiction requirement backs which clause — so an admin editing a draft can see the citation, not just the generated text.',
  '["Public, token-scoped handbook share links: employees open the link, read the handbook, and acknowledge it — no account needed.", "Handbook Pilot drafting view gained reading width + inline editing of drafts before promotion.", "Intelligent handbook viewer: compliance provenance surfaces inline in the handbook view — see which jurisdiction requirement a clause traces back to.", "Draft prose no longer leaks internal corpus-id tags into what the admin reads."]',
  '["Company → Handbooks → generate a share link → send to employees for acknowledgement (tracked per employee).", "Handbook Pilot → open a draft → the handbook view now shows citation provenance alongside the drafted text, and supports editing inline."]',
  NULL,
  NULL,
  NULL
),

(
  'risk-analysis-depth-hardening',
  8,
  '2026-07-11',
  'Broker',
  'Risk analysis depth — TCOR + retention, COI tracking, D&O readiness, ACORD forms, risk-index confidence bands',
  'A broad breadth-and-depth pass on the broker risk-analysis stack: total-cost-of-risk with retention modeling, certificate-of-insurance tracking, D&O readiness scoring, ACORD form generation, and a confidence band on the composite risk index (so a thinly-documented client shows a wider band, not a falsely precise single number) — followed by a review pass fixing correctness and safe-degradation issues found in the new surfaces.',
  '["TCOR (total cost of risk) + retention modeling on the broker client view.", "Certificate-of-insurance (COI) tracking.", "D&O readiness scoring.", "ACORD form generation (standard insurance-industry submission forms).", "risk_index now carries a confidence band (CI), not a bare number — reflects how much real data backs the score.", "Cohort comparison de-stubbed (was placeholder data), WC credibility modifier, driver frequency/severity split.", "Review-pass fixes: tenure math correction, external-reserve confidence handling, 503 guards on the new routes, COI list crash fix, TCOR event-loop block fix, ACORD schema fix."]',
  '["Broker → client detail: new TCOR, COI, D&O, and ACORD sections alongside existing loss-development/limit-adequacy/property tooling.", "Risk index now shows its confidence band wherever the composite score is displayed."]',
  NULL,
  '["This shipped as two passes (breadth, then depth) plus a dedicated review-findings pass — the review pass is what closed the correctness bugs, not a separate feature."]',
  'action-needed'
);

COMMIT;
