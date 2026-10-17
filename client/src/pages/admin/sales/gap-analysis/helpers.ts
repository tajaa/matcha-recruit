export function complexityBandClass(band: string): string {
  switch (band) {
    case 'Severe': return 'bg-red-500/15 text-red-300 border-red-500/30'
    case 'High': return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
    case 'Moderate': return 'bg-blue-500/15 text-blue-300 border-blue-500/30'
    default: return 'bg-zinc-700/40 text-zinc-300 border-zinc-600/40' // Low
  }
}
