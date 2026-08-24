export function formatCount(value: number): string {
  if (value < 1000) return String(value)
  if (value < 1_000_000) return `${trimZero(value / 1000)}K`
  if (value < 1_000_000_000) return `${trimZero(value / 1_000_000)}M`
  return `${trimZero(value / 1_000_000_000)}B`
}

function trimZero(value: number): string {
  return value.toFixed(1).replace(/\.0$/, '')
}
