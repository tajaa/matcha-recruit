// Job-description body content, split by category.
// Public import path ('./jobDescriptionsContent') and exported symbols
// (JDContent, EEO_STATEMENT, JD_CONTENT) are unchanged.
//
// NOTE: this directory must NOT be named `jobDescriptions` — that collides
// with the sibling page `JobDescriptions.tsx` on case-insensitive
// filesystems (macOS), where `./jobDescriptions` silently resolves to the
// page component instead of this index. Distinct from `jobDescriptionsData.ts`,
// which holds the listing metadata (JOB_DESCRIPTIONS / INDUSTRIES).
import type { JDContent } from './types'
import { hospitality } from './hospitality'
import { healthcare } from './healthcare'
import { retail } from './retail'
import { foodService } from './foodService'
import { trades } from './trades'
import { manufacturing } from './manufacturing'
import { administrative } from './administrative'
import { technology } from './technology'
import { sales } from './sales'

export type { JDContent } from './types'
export { EEO_STATEMENT } from './eeo'

export const JD_CONTENT: Record<string, JDContent> = {
  ...hospitality,
  ...healthcare,
  ...retail,
  ...foodService,
  ...trades,
  ...manufacturing,
  ...administrative,
  ...technology,
  ...sales,
}
