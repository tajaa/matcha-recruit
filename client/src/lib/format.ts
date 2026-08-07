export function formatDuration(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return '--:--'
  const total = Math.round(sec)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function formatMoney(amount: number | string | null | undefined, currency: string): string {
  if (amount == null) return '--'
  const value = typeof amount === 'string' ? parseFloat(amount) : amount
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(value)
}

export function displayIsrc(isrc: string | null | undefined): string {
  if (!isrc || isrc.length !== 12) return isrc ?? ''
  return `${isrc.slice(0, 2)}-${isrc.slice(2, 5)}-${isrc.slice(5, 7)}-${isrc.slice(7, 12)}`
}
