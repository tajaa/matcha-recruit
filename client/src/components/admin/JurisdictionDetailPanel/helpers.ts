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

