export const str = (v: unknown): string => (typeof v === 'string' ? v : '')
export const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
export const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}
export const isOn = (v: unknown): boolean => v === true
