// Barrel: the compliance HTTP/API client. Import path `api/compliance`; every
// exported symbol preserved from the pre-flatten `api/compliance/compliance`.
export * from './types'
export * from './locations'
export * from './calendar'
export * from './requirements'
export * from './audit'
export * from './credentials'
export * from './alerts'
export * from './summary'
export * from './checks'
export * from './posters'
export * from './qualityAudit'
export * from './regulatory'
export * from './payer'
export * from './keyCoverage'
export * from './admin'
// Labels moved to data/complianceLabels.ts (not an api/ concern) but stay
// re-exported here — the pre-flatten barrel exported them via
// `./compliance/labels`, and this comment's "every symbol preserved" claim
// depends on it.
export { JURISDICTION_LEVEL_LABELS, RATE_TYPE_LABELS } from '../../data/complianceLabels'
