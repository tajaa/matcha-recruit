export type AutoPRProgressKind =
  | 'ready'
  | 'awaiting_answers'
  | 'already_fixed'
  | 'migration_required'
  | 'policy_blocked'
  | 'external_dependency'
  | 'status'

export interface AutoPRProgressBanner {
  kind: AutoPRProgressKind
  message: string
}

/** Convert the durable progress_note written by kanban-autopr into a short,
 * visible card-face status. Legacy `from auto setup` notes remain recognized
 * so deploying the UI does not require rewriting every historical ticket. */
export function autoPRProgressBanner(
  progressNote: string | null | undefined,
  prNumber?: number | null,
): AutoPRProgressBanner | null {
  const note = progressNote?.trim()
  if (!note || !/^(?:🤖\s*)?auto setup\b|^from auto setup\b/i.test(note)) return null

  const pr = prNumber ? `PR #${prNumber}` : 'the draft PR'
  if (/awaiting answers|answers needed/i.test(note)) {
    return { kind: 'awaiting_answers', message: `Blocked — answer questions on ${pr}` }
  }
  if (/\balready_fixed\b|already fixed/i.test(note)) {
    return { kind: 'already_fixed', message: 'No new PR — already fixed; verify/deploy or add evidence' }
  }
  if (/\bmigration_required\b|migration required/i.test(note)) {
    return { kind: 'migration_required', message: 'Human action — migration required; no PR was created' }
  }
  if (/\bpolicy_blocked\b|policy blocked/i.test(note)) {
    return { kind: 'policy_blocked', message: 'Human action — policy blocked; no PR was created' }
  }
  if (/\bexternal_dependency\b|external dependency/i.test(note)) {
    return { kind: 'external_dependency', message: 'Waiting on an external dependency; no PR was created' }
  }
  if (/ready for review/i.test(note)) {
    return { kind: 'ready', message: prNumber ? `PR #${prNumber} is ready for review` : 'Ready for review' }
  }
  return { kind: 'status', message: 'Automation status is recorded on this ticket' }
}
