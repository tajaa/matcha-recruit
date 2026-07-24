/**
 * Admin-facing catalog of sellable feature flags, grouped for display.
 *
 * Shared by the per-company toggle grid (pages/admin/Features.tsx) and the
 * product builder (pages/admin/Products.tsx) so both show the same names for
 * the same flags. The backend list (GET /admin/products → available_features,
 * derived from DEFAULT_COMPANY_FEATURES) stays authoritative for what MAY be
 * sold; this map only supplies human labels.
 */
export const FEATURE_GROUPS: { label: string; features: Record<string, string> }[] = [
  {
    label: 'Core HR',
    features: {
      policies: 'Policies',
      handbooks: 'Handbooks',
      compliance: 'Compliance',
      employees: 'Employees',
      offer_letters: 'Offer Letters',
      er_copilot: 'ER Copilot',
      incidents: 'Incidents',
      time_off: 'Time Off',
      accommodations: 'Accommodations',
      interview_prep: 'Interview Prep',
      risk_assessment: 'Risk Assessment',
      training: 'Training',
      i9: 'I-9 Verification',
      cobra: 'COBRA',
      separation_agreements: 'Separation Agreements',
      credential_templates: 'Credential Templates',
      discipline: 'Performance Action',
      employee_schedule: 'Employee Schedule (shift scheduling — assignments, templates, swap/drop requests)',
      schedule_intelligence: 'Schedule Intelligence (incident correlation, Fair Workweek exposure, qualified coverage — needs Employee Schedule too)',
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
      inventory: 'Inventory',
      werk_lite: 'Werk Lite (work-chat surface — needs Matcha Work too)',
      werk_lite_calls_all_members: 'Werk Lite — any member can start calls',
      hr_pilot: 'HR Pilot (thread mode — handbook-grounded supervisor guidance + hard-stop HR escalation gate)',
    },
  },
  {
    label: 'Risk & Underwriting',
    features: {
      workforce_compliance: 'Workforce Compliance (pay transparency · AI-audit · biometric)',
      risk_profile: 'Risk Profile (client-facing composite risk index)',
      resident_care: 'Resident-Care Risk (healthcare/senior-living asset)',
      controls_evidence: 'Proof of Controls (controls-evidence register + packet)',
      limit_adequacy: 'Limit Adequacy & Contract Review (limits vs contracts)',
      driver_risk: 'Driver Risk (fleet MVR scoring — commercial auto)',
    },
  },
  {
    label: 'AI Pilots',
    features: {
      ir_voice_intake: 'IR Voice Intake (dictate on create + magic-link forms)',
      legal_defense: 'Legal Pilot (AI litigation-evidence packets)',
      handbook_pilot: 'Handbook Pilot (AI handbook/policy generation)',
      analysis_pilot: 'Analysis Pilot (general data-analysis chat — CSV/XLSX/PDF, deterministic metrics)',
    },
  },
]

export const FEATURE_LABELS: Record<string, string> = Object.fromEntries(
  FEATURE_GROUPS.flatMap((g) => Object.entries(g.features))
)

export const FEATURE_KEYS = Object.keys(FEATURE_LABELS)
