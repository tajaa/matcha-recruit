export const MAX_REQUIRED_STAFF = 99
export const MAX_BREAK_MINUTES = 1440

type ShiftFieldInput = {
  date: string
  start: string
  end: string
  requiredStaff: string
  breakMinutes: string
}

type ShiftFieldValidation =
  | { valid: true; requiredStaff: number; breakMinutes: number | undefined }
  | { valid: false; error: string }

const TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/

export function validateShiftFields({ date, start, end, requiredStaff, breakMinutes }: ShiftFieldInput): ShiftFieldValidation {
  if (!date.trim()) return { valid: false, error: 'Date is required' }
  if (!start.trim() || !end.trim()) return { valid: false, error: 'Start and end times are required' }
  if (!TIME_PATTERN.test(start) || !TIME_PATTERN.test(end)) {
    return { valid: false, error: 'Start and end times must be valid' }
  }

  const parsedRequiredStaff = Number(requiredStaff)
  if (
    requiredStaff.trim() === ''
    || !Number.isInteger(parsedRequiredStaff)
    || parsedRequiredStaff < 1
    || parsedRequiredStaff > MAX_REQUIRED_STAFF
  ) {
    return { valid: false, error: `Staff needed must be a whole number from 1 to ${MAX_REQUIRED_STAFF}` }
  }

  if (breakMinutes.trim() === '') {
    return { valid: true, requiredStaff: parsedRequiredStaff, breakMinutes: undefined }
  }

  const parsedBreakMinutes = Number(breakMinutes)
  if (
    !Number.isInteger(parsedBreakMinutes)
    || parsedBreakMinutes < 0
    || parsedBreakMinutes > MAX_BREAK_MINUTES
  ) {
    return { valid: false, error: `Planned break must be a whole number from 0 to ${MAX_BREAK_MINUTES} minutes` }
  }

  return { valid: true, requiredStaff: parsedRequiredStaff, breakMinutes: parsedBreakMinutes }
}
