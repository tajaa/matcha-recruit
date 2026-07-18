// Barrel: the compliance HTTP/API client, split by domain into ./compliance/*.
// Public import path (`api/compliance/compliance`) and every exported symbol are
// preserved — re-export everything from the sibling domain modules.

export * from './compliance/types'
export * from './compliance/locations'
export * from './compliance/calendar'
export * from './compliance/requirements'
export * from './compliance/credentials'
export * from './compliance/alerts'
export * from './compliance/summary'
export * from './compliance/checks'
export * from './compliance/posters'
export * from './compliance/labels'
export * from './compliance/quality-audit'
export * from './compliance/regulatory'
export * from './compliance/payer'
export * from './compliance/key-coverage'
export * from './compliance/admin'
