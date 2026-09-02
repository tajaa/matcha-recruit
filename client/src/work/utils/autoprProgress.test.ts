import { describe, expect, it } from 'vitest'
import { autoPRProgressBanner } from './autoprProgress'

describe('autoPRProgressBanner', () => {
  it('recognizes legacy question notes and names the PR', () => {
    expect(autoPRProgressBanner(
      'from auto setup · build 552 · prod fbd7b74 · PR #318 · 🟠 C56 · awaiting answers',
      318,
    )).toEqual({ kind: 'awaiting_answers', message: 'Blocked — answer questions on PR #318' })
  })

  it.each([
    ['already_fixed', 'already_fixed', 'No new PR — already fixed; verify/deploy or add evidence'],
    ['migration_required', 'migration_required', 'Human action — migration required; no PR was created'],
    ['policy_blocked', 'policy_blocked', 'Human action — policy blocked; no PR was created'],
    ['external_dependency', 'external_dependency', 'Waiting on an external dependency; no PR was created'],
  ] as const)('makes %s no-spec states explicit', (_name, reason, message) => {
    const note = `🤖 AUTO SETUP · NO PR: HUMAN ACTION REQUIRED · [autopr:no-spec 2026-08-27T00:00:00Z] ${reason}`
    expect(autoPRProgressBanner(note)).toEqual({ kind: reason, message })
  })

  it('does not turn a human progress note into an AutoPR banner', () => {
    expect(autoPRProgressBanner('Waiting for design approval')).toBeNull()
  })
})
