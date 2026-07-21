import {
  AlertTriangle, BadgeCheck, BarChart3, Boxes, Building2, CalendarClock, CalendarDays,
  Car, ClipboardList, FileCheck2, FileSearch, FileSignature, FileText, GraduationCap,
  Gavel, HeartPulse, MessageSquare, Scale, Shield, ShieldCheck, Siren,
  Sparkles, TrendingUp, Users, Wallet,
} from 'lucide-react'
import type { NavIcon } from '../components/sidebars/SidebarShell'
import type { ProductDefinition } from '../types/dashboard'

/**
 * feature flag → the page that flag unlocks.
 *
 * The single place that knows what a sellable feature LOOKS like in the nav.
 * A product composed in /admin/products derives its whole sidebar from this
 * map, so shipping a new page means adding one line here, not a new sidebar
 * file per product.
 *
 * Flags with no standalone page (osha_logs lives inside IR, hris_* are
 * settings, werk_lite_calls_all_members is a policy toggle) are deliberately
 * absent — they're still sellable, they just don't produce a nav row.
 */
export type ProductNavEntry = { to: string; icon: NavIcon; label: string }

export const PRODUCT_NAV_CATALOG: Record<string, ProductNavEntry> = {
  incidents: { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  osha_logs: { to: '/app/ir/osha', icon: ClipboardList, label: 'OSHA Logs' },
  carrier_quotes: { to: '/app/ir/insurance', icon: ShieldCheck, label: 'Insurance' },
  employees: { to: '/app/employees', icon: Users, label: 'Employees' },
  employee_schedule: { to: '/app/employee-schedule', icon: CalendarDays, label: 'Schedule' },
  handbooks: { to: '/app/handbooks', icon: FileText, label: 'Handbooks' },
  handbook_audit: { to: '/app/handbooks', icon: FileSearch, label: 'Handbook Audit' },
  handbook_pilot: { to: '/app/handbook-pilot', icon: Sparkles, label: 'Handbook Pilot' },
  policies: { to: '/app/policies', icon: FileText, label: 'Policies' },
  compliance: { to: '/app/compliance', icon: Shield, label: 'Compliance' },
  compliance_lite: { to: '/app/compliance', icon: Shield, label: 'Compliance' },
  training: { to: '/app/training', icon: GraduationCap, label: 'Training' },
  discipline: { to: '/app/discipline', icon: Gavel, label: 'Performance Action' },
  accommodations: { to: '/app/accommodations', icon: HeartPulse, label: 'Accommodations' },
  er_copilot: { to: '/app/er-copilot', icon: MessageSquare, label: 'ER Copilot' },
  credential_templates: { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing' },
  labor_relations: { to: '/app/labor', icon: Scale, label: 'Labor Relations' },
  risk_assessment: { to: '/app/risk-assessment', icon: TrendingUp, label: 'Risk Assessment' },
  risk_profile: { to: '/app/risk-profile', icon: TrendingUp, label: 'Risk Profile' },
  workforce_compliance: { to: '/app/workforce-compliance', icon: FileCheck2, label: 'Workforce Compliance' },
  resident_care: { to: '/app/resident-care', icon: HeartPulse, label: 'Resident-Care Risk' },
  controls_evidence: { to: '/app/controls-evidence', icon: ShieldCheck, label: 'Proof of Controls' },
  limit_adequacy: { to: '/app/limit-adequacy', icon: Scale, label: 'Limit Adequacy' },
  driver_risk: { to: '/app/driver-risk', icon: Car, label: 'Driver Risk' },
  tcor: { to: '/app/tcor', icon: Wallet, label: 'Total Cost of Risk' },
  coi_tracking: { to: '/app/coi', icon: FileSignature, label: 'Certificate Tracking' },
  do_readiness: { to: '/app/management-liability', icon: Shield, label: 'D&O Readiness' },
  acord_forms: { to: '/app/acord', icon: FileText, label: 'ACORD Forms' },
  property: { to: '/app/property', icon: Building2, label: 'Commercial Property' },
  legal_defense: { to: '/app/legal-pilot', icon: Siren, label: 'Legal Pilot' },
  analysis_pilot: { to: '/app/analysis-pilot', icon: BarChart3, label: 'Analysis Pilot' },
  matcha_work: { to: '/work', icon: Boxes, label: 'Matcha Work' },
  i9: { to: '/app/onboarding', icon: FileCheck2, label: 'Onboarding & I-9' },
  cobra: { to: '/app/employees', icon: HeartPulse, label: 'COBRA' },
  separation_agreements: { to: '/app/employees', icon: FileSignature, label: 'Separations' },
  benefits_admin: { to: '/app/employees', icon: HeartPulse, label: 'Benefits' },
}

/** Nav rows every product gets regardless of features. */
export const PRODUCT_ALWAYS_NAV: ProductNavEntry[] = [
  { to: '/app/company', icon: Building2, label: 'Company' },
]

/** Compliance calendar rides any of the compliance-family flags. */
const COMPLIANCE_CALENDAR: ProductNavEntry = {
  to: '/app/compliance-calendar', icon: CalendarClock, label: 'Compliance Calendar',
}

/**
 * Ordered nav for a product: the admin's saved ordering when there is one,
 * otherwise catalog order over the granted features.
 *
 * Deduped by route — several flags legitimately point at the same page
 * (`compliance`/`compliance_lite`, `handbooks`/`handbook_audit`), and two rows
 * to the same URL would both light up as active.
 */
export function buildProductNav(product: ProductDefinition): ProductNavEntry[] {
  const granted = new Set(product.features)
  const ordered: ProductNavEntry[] = []
  const seen = new Set<string>()

  const push = (entry: ProductNavEntry | undefined) => {
    if (!entry || seen.has(entry.to)) return
    seen.add(entry.to)
    ordered.push(entry)
  }

  if (product.nav?.length) {
    for (const item of product.nav) {
      const base = PRODUCT_NAV_CATALOG[item.feature]
      if (!base) continue
      push(item.label ? { ...base, label: item.label } : base)
    }
  } else {
    for (const [feature, entry] of Object.entries(PRODUCT_NAV_CATALOG)) {
      if (granted.has(feature)) push(entry)
    }
  }

  if (granted.has('compliance') || granted.has('compliance_lite')) push(COMPLIANCE_CALENDAR)
  for (const entry of PRODUCT_ALWAYS_NAV) push(entry)
  return ordered
}
