export function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString()
}

export function fmtRelative(iso: string | null): string {
  if (!iso) return '—'
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// Pull the first statute citation out of research text (deterministic, no AI) to
// prefill the Codify modal. Handles the common US forms; admin edits/confirms
// before submit — this is a legal record, never auto-filed.
export function extractCitation(...texts: (string | null | undefined)[]): string {
  const hay = texts.filter(Boolean).join('  ')
  const patterns = [
    /\b\d+\s+U\.?S\.?C\.?\s+§+\s*[\d.\-()a-z]+/i,        // 29 U.S.C. § 654
    /\b\d+\s+C\.?F\.?R\.?\s+§+\s*[\d.\-()a-z]+/i,        // 29 C.F.R. § 1910
    /\bC\.?R\.?S\.?\s+§+\s*[\d.\-()a-z]+/i,               // C.R.S. § 12-220-101
    /\bCal\.?\s+[A-Za-z.&\s]+Code\s+§+\s*[\d.\-()a-z]+/i, // Cal. Lab. Code § 246
    /\b\d+\s+CCR\s+[\d.\-]+/i,                            // 3 CCR 709-1
    /§+\s*[\d]+[\d.\-()a-z]*/i,                           // generic § 12-220-101
  ]
  for (const re of patterns) {
    const m = hay.match(re)
    if (m) return m[0].replace(/\s+/g, ' ').trim()
  }
  return ''
}

// Deep-link into the Coverage tab at a jurisdiction (state/city) + industry —
// used by Pipeline rows to send the admin to the exhaustiveness/codify surfaces
// for that jurisdiction.
export function coverageLink(state?: string | null, city?: string | null, industry = 'healthcare') {
  const p = new URLSearchParams({ view: 'coverage', industry })
  if (state) p.set('state', state)
  if (city) p.set('city', city)
  return `/admin/studio?${p.toString()}`
}

// Deep-link into the Library shelf for a coordinate — the post-codify "did it
// land in jurisdiction-data?" proof. `industry` focuses that detail section
// ('general' → General employment law); omit for a plain jurisdiction open.
export function libraryLink(state?: string | null, city?: string | null,
                            industry?: string | null, reqId?: string | null) {
  const p = new URLSearchParams({ view: 'library' })
  if (state) p.set('state', state)
  if (city) p.set('city', city)
  if (industry) p.set('industry', industry)
  if (reqId) p.set('req', reqId)   // scroll to + highlight this exact requirement
  return `/admin/studio?${p.toString()}`
}
