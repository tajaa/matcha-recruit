/**
 * Admin-facing catalog of sellable feature flags, grouped for display.
 *
 * Shared by the per-company toggle grid (pages/admin/Features.tsx) and the
 * product builder (pages/admin/Products.tsx) so both show the same names for
 * the same flags. The backend list (GET /admin/products → available_features,
 * derived from DEFAULT_COMPANY_FEATURES) stays authoritative for what MAY be
 * sold; this map only supplies human labels. A backend flag this map doesn't
 * name still shows up, in the "Other" group (see `withOtherGroup`).
 */
export type FeatureGroup = { label: string; features: Record<string, string> }

export const FEATURE_GROUPS: FeatureGroup[] = [
  {
    label: 'Core HR',
    features: {
      policies: 'Policies',
      handbooks: 'Handbooks',
      handbook_audit: 'Handbook Audit (gap analyzer)',
      handbook_watch: 'Handbook Watch (scheduled freshness sweeps + alerts)',
      compliance: 'Compliance',
      compliance_lite: 'Compliance Lite (read-only requirement viewers)',
      employees: 'Employees',
      offer_letters: 'Offer Letters',
      er_copilot: 'ER Copilot',
      incidents: 'Incidents',
      safety_meetings: 'Safety Meetings (transcribed toolbox talks + manager sign-off)',
      osha_logs: 'OSHA Logs (interactive 300/301/300A recordkeeping)',
      osha_export: 'OSHA 300 Log CSV Export (download-only)',
      osha_auto_report: 'OSHA Auto-Report (ITA electronic submission)',
      ir_magic_links: 'IR Magic Links (anonymous report + location + info-request links)',
      ir_copilot: 'IR Copilot & AI Analysis',
      symlink: 'Sym-Link (guided task links — credential upload, manager review, info update)',
      time_off: 'Time Off',
      risk_assessment: 'Risk Assessment',
      training: 'Training',
      i9: 'I-9 Verification',
      cobra: 'COBRA',
      separation_agreements: 'Separation Agreements',
      credential_templates: 'Credential Templates',
      employee_schedule: 'Employee Schedule (shift scheduling — assignments, templates, swap/drop requests)',
      schedule_intelligence: 'Schedule Intelligence (incident correlation, Fair Workweek exposure, qualified coverage — needs Employee Schedule too)',
      labor_cost: 'Labor Cost (scheduled wage cost, overtime-aware — needs Employee Schedule too)',
      schedule_autopilot: 'Schedule Autopilot (forecast-driven week generation — needs Employee Schedule, Huume and Matcha Work)',
      benefits_admin: 'Benefits (roster ingest, eligibility exceptions, renewal-risk radar)',
      labor_relations: 'Labor Relations (CBAs, grievances, bargaining units)',
    },
  },
  {
    label: 'HRIS',
    features: {
      hris_gusto: 'HRIS — Gusto (direct)',
      hris_finch: 'HRIS — Finch (Rippling, BambooHR, ADP…)',
      hris_deductions: 'HRIS — Deductions/benefits write (Finch)',
      hris_import: 'HRIS Import (legacy — enables both)',
    },
  },
  {
    label: 'Matcha Work',
    features: {
      matcha_work: 'Matcha Work',
      hr_pilot: 'HR Pilot (thread mode — handbook-grounded supervisor guidance + hard-stop HR escalation gate)',
      huume: 'Huume (agentic thread mode — offer letters, onboarding plans, HR-ops actions, Legal/Handbook Pilot in chat) — needs Matcha Work too',
      huume_code: 'Huume Code (draft PRs from a collab chat — internal only) — needs Matcha Work too',
      sym_chat: 'Sym-chat (private-tunnel group chats that settle a meeting time or a decision) — needs Matcha Work too',
      matcha_drive: 'Matcha Drive (company + HR document store with per-folder access) — needs Matcha Work too',
      hr_cases: 'HR Cases (incident → write-up → approval → signed copy) — needs Matcha Work and Matcha Drive',
      paid_channel_creator: 'Paid Channels (Stripe-gated paid channel creation)',
      channel_job_postings: 'Channel Job Postings (Stripe-gated)',
    },
  },
  {
    label: 'Matcha Ops',
    features: {
      matcha_ops: 'Matcha Ops',
      ems: 'Ops — Events (channel event logging via @huume)',
      inventory: 'Ops — Inventory (channel stock tracking via @huume)',
      inventory_voice: 'Ops — Inventory Voice Audit (Gemini count dictation) — needs Inventory too',
      sales_intake: 'Ops — Sales Intake (POS exports and variance reporting) — needs Inventory too',
      inventory_forecasting: 'Ops — Inventory Forecasting (demand and replenishment recommendations) — needs Sales Intake too',
      inventory_waste: 'Ops — Inventory Waste & Shrinkage (waste log, variance, predictive par) — needs Inventory too',
      employee_schedule: 'Ops — Employee Schedule',
      schedule_intelligence: 'Ops — Schedule Intelligence — needs Employee Schedule too',
      labor_cost: 'Ops — Labor Cost — needs Employee Schedule too',
      schedule_autopilot: 'Ops — Schedule Autopilot — needs Employee Schedule, Huume and Matcha Work',
      matcha_ops_calls_all_members: 'Matcha Ops — any member can start calls',
      werk_lite: 'Werk Lite (Ops channels + Work boards)',
      werk_lite_calls_all_members: 'Werk Lite — any member can start calls',
    },
  },
  {
    label: 'Risk & Underwriting',
    features: {
      workforce_compliance: 'Workforce Compliance (pay transparency · AI-audit · biometric)',
      risk_profile: 'Risk Profile (client-facing composite risk index)',
      controls_evidence: 'Proof of Controls (controls-evidence register + packet)',
      limit_adequacy: 'Limit Adequacy & Contract Review (limits vs contracts)',
      property: 'Property (SOV/COPE grading, insurance-to-value, cat perils)',
      tcor: 'TCOR (total cost of risk + retention optimizer)',
      coi_tracking: 'COI Tracking (certificate capture, limit check, expiry alerts)',
      do_readiness: 'D&O Readiness (management-liability readiness score)',
      acord_forms: 'ACORD Forms (125/126/130/140 equivalents)',
      carrier_quotes: 'Carrier Quotes (quote + bind)',
    },
  },
  {
    label: 'AI Pilots',
    features: {
      ir_voice_intake: 'IR Voice Intake (dictate on create + magic-link forms)',
      ir_chat_intake: 'IR Chat Intake (authenticated + magic-link reports)',
      legal_defense: 'Legal Pilot (AI litigation-evidence packets)',
      handbook_pilot: 'Handbook Pilot (AI handbook/policy generation)',
      analysis_pilot: 'Analysis Pilot (general data-analysis chat — CSV/XLSX/PDF, deterministic metrics)',
      ask_hr: 'Ask HR (employee-portal HR Pilot, coworker data redacted)',
    },
  },
]

export const FEATURE_LABELS: Record<string, string> = Object.fromEntries(
  FEATURE_GROUPS.flatMap((g) => Object.entries(g.features))
)

export const FEATURE_KEYS = Object.keys(FEATURE_LABELS)

const FEATURE_KEY_SET = new Set(FEATURE_KEYS)

export const OTHER_GROUP_LABEL = 'Other'

/** The catalog's name for a flag, or the raw key when the catalog has none. */
export function featureLabel(key: string): string {
  return FEATURE_KEY_SET.has(key) ? FEATURE_LABELS[key] : key
}

/**
 * FEATURE_GROUPS plus an "Other" group holding every key in `backendKeys`
 * that the catalog doesn't name, labelled with the raw key. The admin pages
 * render their toggles from groups, so without this a flag added to the
 * backend's DEFAULT_COMPANY_FEATURES but not to this file could be neither
 * seen nor toggled (17 were, until this group existed).
 */
export function withOtherGroup(backendKeys: Iterable<string>): FeatureGroup[] {
  const other = [...new Set(backendKeys)].filter((key) => !FEATURE_KEY_SET.has(key)).sort()
  if (other.length === 0) return FEATURE_GROUPS
  return [
    ...FEATURE_GROUPS,
    { label: OTHER_GROUP_LABEL, features: Object.fromEntries(other.map((key) => [key, key])) },
  ]
}

/**
 * Mirrors backend `FEATURE_REQUIRES` (server/app/core/feature_flags.py) —
 * flags that do nothing without another flag also being on. The backend is
 * the real gate (`assert_feature_dependencies`, checked on every write);
 * this copy only drives the admin toggle grid's disabled-state + tooltip so
 * the UI doesn't let an admin stage a dead configuration in the first place.
 */
export const FEATURE_REQUIRES: Record<string, string[]> = {
  huume: ['matcha_work'],
  huume_code: ['matcha_work'],
  sym_chat: ['matcha_work'],
  matcha_drive: ['matcha_work'],
  hr_cases: ['matcha_work', 'matcha_drive'],
  ems: ['matcha_ops'],
  inventory: ['matcha_ops'],
  inventory_voice: ['inventory'],
  sales_intake: ['inventory'],
  inventory_forecasting: ['inventory', 'sales_intake'],
  inventory_waste: ['inventory'],
  schedule_intelligence: ['employee_schedule'],
  labor_cost: ['employee_schedule'],
  schedule_autopilot: ['employee_schedule', 'huume', 'matcha_work'],
  matcha_ops_calls_all_members: ['matcha_ops'],
  werk_lite: ['matcha_ops', 'matcha_work'],
  // osha_export/osha_auto_report/ir_magic_links/ir_copilot are deliberately
  // NOT here even though each needs incidents/osha_logs to do anything — see
  // the backend FEATURE_REQUIRES comment (feature_flags.py) for why: the
  // route-level gates already make them inert without their parent, and
  // ir_magic_links/ir_copilot default True (subtractive), so enforcing the
  // dependency here would disable-block incidents on any company with either
  // still at its default.
}

/**
 * Apply one feature toggle with its dependency closure. Product composition
 * uses this to keep drafts valid before the backend validates them; the
 * per-company toggle grid keeps its stricter disabled-state behavior because
 * it must not silently change another feature.
 */
export function applyFeatureToggle(
  features: Record<string, boolean>,
  feature: string,
  enabled: boolean,
): Record<string, boolean> {
  const next = { ...features }

  if (enabled) {
    const enable = (key: string, visiting: Set<string>) => {
      if (visiting.has(key)) return
      visiting.add(key)
      for (const requirement of FEATURE_REQUIRES[key] ?? []) {
        enable(requirement, visiting)
      }
      next[key] = true
      visiting.delete(key)
    }
    enable(feature, new Set())
  } else {
    const disable = (key: string, visiting: Set<string>) => {
      if (visiting.has(key)) return
      visiting.add(key)
      next[key] = false
      for (const dependent of Object.entries(FEATURE_REQUIRES)
        .filter(([, requirements]) => requirements.includes(key))
        .map(([candidate]) => candidate)) {
        disable(dependent, visiting)
      }
      visiting.delete(key)
    }
    disable(feature, new Set())
  }
  return next
}
