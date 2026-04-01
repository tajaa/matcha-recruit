export const MODEL_OPTIONS = [
  { id: 'gemini-3.1-flash-lite-preview', label: 'Flash Lite 3.1' },
  { id: 'gemini-3-flash-preview', label: 'Flash 3.0' },
  { id: 'gemini-3.1-pro-preview', label: 'Pro 3.1' },
] as const

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}
