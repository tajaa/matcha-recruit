import type { AIScope } from '../../../../api/admin/adminOnboarding'
export function isScopeEmpty(s: AIScope | null | undefined): boolean {
  if (!s) return true
  return (
    !s.naics_sector
    && (s.compliance_categories?.length || 0) === 0
    && (s.required_certifications?.length || 0) === 0
    && (s.required_licenses?.length || 0) === 0
    && (s.applicable_jurisdictions?.length || 0) === 0
  )
}

export const ALL_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM',
  'NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA',
  'WV','WI','WY',
]
