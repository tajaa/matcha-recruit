import type { RiskIssue } from '../../../types/compliance'

// The cockpit now sits inside the page frame, which is itself bg-zinc-950 —
// so panels can no longer BE zinc-950 or they'd dissolve into their own
// canvas. zinc-900/40 lifts them off it and survives the light theme, where
// the neutral ramp inverts (zinc-900 → #ffffff) and a white/x overlay would
// vanish instead. Matches the surfaces already used further down this file.
export const PANEL = 'rounded-lg border border-white/[0.06] bg-zinc-900/40'

// Severity semantics — the spine of the whole surface.
export const SEV = {
  critical: { rail: 'border-l-red-500', dot: 'bg-red-500', text: 'text-red-400', chip: 'text-red-300' },
  high: { rail: 'border-l-amber-500', dot: 'bg-amber-500', text: 'text-amber-400', chip: 'text-amber-300' },
  moderate: { rail: 'border-l-zinc-500', dot: 'bg-zinc-500', text: 'text-zinc-400', chip: 'text-zinc-300' },
} as const

export const SOURCE_LABEL: Record<RiskIssue['source'], string> = {
  wage: 'Wage & Hour',
  credential: 'Credentialing',
  incident: 'Safety / OSHA',
  alert: 'Regulatory',
  requirement: 'Requirement',
}

export const FIX_VERB: Record<RiskIssue['source'], string> = {
  wage: 'Fix pay', credential: 'Renew', incident: 'Open incident', alert: 'Assign owner',
  requirement: 'Review',
}

// Plain-language help for the manager, matched to what each element controls.
export const HELP = {
  openIssues: 'Everything currently out of compliance, split by urgency. Critical is a live legal violation (e.g. paid below minimum wage); high/moderate are things to get ahead of, like a license expiring soon.',
  exposure: 'A rough dollar range of the statutory penalties tied to your open violations, summed from the enforcing agencies’ published fines. It’s an estimate to size the risk, not a bill — some laws don’t name a figure (shown as "unquantified").',
  affected: 'How many of your employees are named in an open issue right now (underpaid, expired license, etc.). Hover the number to see who.',
  nextDeadline: 'The soonest thing with a due date — a license expiry, an alert deadline, or a new law taking effect. Fix these before they become violations.',
  actionQueue: 'Your to-do list, worst first. Click Fix to jump straight to the exact record (the underpaid employee, the incident) and correct it. When you do, the issue clears itself and is logged in Remediation history.',
  fix: 'Opens the exact record where you fix this — the employee’s pay, their license, or the incident. Once the data is corrected the issue leaves this list automatically.',
  dismiss: 'Use only if this isn’t a real violation (e.g. the employee is correctly classified as exempt). You must give a reason; it’s recorded. It comes back on its own if the underlying numbers change.',
  getAhead: 'Things coming up — new laws and deadlines — so you can act before they turn into violations.',
  history: 'The documented record of every issue you’ve resolved or dismissed: what it was, when, how, and who. This is your paper trail if a claim or audit ever asks "what did you do about it?"',
} as const
