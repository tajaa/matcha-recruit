export const privacyReasonLabel: Record<string, string> = {
  intimate_injury: 'Intimate injury',
  sexual_assault: 'Sexual assault',
  mental_illness: 'Mental illness',
  infectious_pathogen: 'HIV / Hepatitis / TB',
  contaminated_sharps: 'Contaminated sharps',
  voluntary_opt_out: 'Employee opt-out',
}

export const classificationLabel: Record<string, string> = {
  death: 'Death',
  days_away: 'Days Away',
  restricted_duty: 'Restricted Duty',
  medical_treatment: 'Medical Treatment',
  loss_of_consciousness: 'Loss of Consciousness',
  significant_injury: 'Significant Injury',
}

export const classificationBadge: Record<string, 'danger' | 'warning' | 'neutral'> = {
  death: 'danger',
  days_away: 'warning',
  restricted_duty: 'warning',
  medical_treatment: 'neutral',
  loss_of_consciousness: 'warning',
  significant_injury: 'warning',
}

// Shown in the pre-export confirm modal. Mirrors the backend EXPORT_DISCLAIMER;
// the server also returns it on a 403 if an un-attested export slips through.
export const EXPORT_DISCLAIMER =
  'This OSHA log was prepared with AI-assisted recordability classification, ' +
  'injury-description cleansing, and Privacy Case name masking. These are aids, ' +
  'not a substitute for your review. Before filing with OSHA or any agency you ' +
  'are responsible for verifying every entry — recordability, day counts, ' +
  'Privacy Case masking, and descriptions. Matcha does not guarantee the ' +
  'accuracy or completeness of generated entries. By exporting you confirm you ' +
  'have reviewed this data and accept responsibility for its accuracy and filing.'

export const missingLabel: Record<string, string> = {
  ein: 'EIN',
  naics: 'NAICS code',
  street_address: 'Street address',
  total_hours_worked: 'Total hours worked',
  unassigned_location: 'a location (excluded from the filing until assigned)',
  // Present-but-malformed values. OSHA rejects the batch on these, so they read
  // as blocking problems alongside the genuinely-absent fields above.
  ein_invalid: 'a valid EIN (must be 9 digits)',
  zip_code_invalid: 'a valid ZIP code (must be 5 or 9 digits)',
}
