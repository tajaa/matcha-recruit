// Barrel for the matcha-work HTTP/API client.
//
// The implementation is split by domain under ./matchaWork/*. This file keeps
// the historical import path (`work/api/matchaWork`) stable and re-exports every
// public symbol so existing importers keep working unchanged.

export * from './matchaWork/threads'
export * from './matchaWork/messaging'
export * from './matchaWork/agent'
export * from './matchaWork/billing'
export * from './matchaWork/recruiting-clients'
export * from './matchaWork/tasks'
export * from './matchaWork/projects'
export * from './matchaWork/candidates'
export * from './matchaWork/project-legacy'
export * from './matchaWork/research'
export * from './matchaWork/invites'
export * from './matchaWork/usage'
export * from './matchaWork/tutor'
export * from './matchaWork/kanban'
