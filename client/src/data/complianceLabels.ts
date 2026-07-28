// ── Label maps ──

export const JURISDICTION_LEVEL_LABELS: Record<string, string> = {
  federal: 'Federal',
  state: 'State',
  county: 'County',
  city: 'City',
}

export const RATE_TYPE_LABELS: Record<string, string> = {
  general: 'General',
  tipped: 'Tipped',
  exempt_salary: 'Exempt Salary',
  // A named sub-state region's own exempt threshold (NY downstate: NYC, Nassau,
  // Suffolk, Westchester carry a higher figure than the rest of the state).
  exempt_salary_regional: 'Exempt Salary (Regional)',
  hotel: 'Hotel',
  fast_food: 'Fast Food',
  healthcare: 'Healthcare',
  large_employer: 'Large Employer',
  small_employer: 'Small Employer',
}
