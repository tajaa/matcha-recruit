// Pure helpers + the SSE reader for the Jurisdiction Detail panel.

import { CATEGORY_LABELS } from '../../../generated/complianceCategories'

// Pretty-print an applicable_industries tag: 'healthcare:oncology' → 'Healthcare · Oncology'.
export function industryLabel(tag: string): string {
  return tag
    .split(':')
    .map((p) => p.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' '))
    .join(' · ')
}

// Anchor slug for a section (URL focus targets these).
export function sectionAnchor(key: string): string {
  return `lib-sec-${key.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`
}

// Anchor for one requirement row (the post-codify deep-link target).
export function reqAnchor(id: string): string {
  return `lib-req-${id}`
}

export function getCategoryLabel(cat: string) {
  return CATEGORY_LABELS[cat] ?? cat
}

// Read an SSE stream with a proper line-buffered decoder. The previous
// inline version called `decoder.decode(value).split('\n')` without buffering,
// which dropped any line that straddled a chunk boundary — including the
// final `data: [DONE]` — so callers never fired their post-stream refetch and
// the UI showed stale (pre-scan) data even after the scan completed.
export async function readSSEStream(
  res: Response,
  onEvent: (ev: any) => void,
  onDone: () => void,
): Promise<void> {
  const reader = res.body?.getReader()
  if (!reader) { onDone(); return }
  const decoder = new TextDecoder()
  let buffer = ''
  let done = false
  const flush = (line: string) => {
    if (!line.startsWith('data: ')) return
    const data = line.slice(6)
    if (data === '[DONE]') { done = true; return }
    try { onEvent(JSON.parse(data)) } catch {}
  }
  while (!done) {
    const { done: streamDone, value } = await reader.read()
    if (streamDone) break
    buffer += decoder.decode(value, { stream: true })
    let nl: number
    while ((nl = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, nl).replace(/\r$/, '')
      buffer = buffer.slice(nl + 1)
      if (line) flush(line)
      if (done) break
    }
  }
  // Flush any trailing line (server usually terminates with \n, but be safe).
  const tail = (buffer + decoder.decode()).trim()
  if (tail && !done) flush(tail)
  onDone()
}
