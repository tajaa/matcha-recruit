import type { HuumeAction, HuumeHandbook, HuumeLegal, HuumeOffer, HuumePlans } from '../types'

export interface HuumeState {
  plans: HuumePlans
  offer?: HuumeOffer
  action?: HuumeAction
  legal?: HuumeLegal
  handbook?: HuumeHandbook
}

/** The one place `current_state`'s untyped Huume keys get cast. The server
 * owns these shapes (services/huume/ writes them); an absent key just means
 * the feature hasn't been used in this thread yet. */
export function getHuumeState(state: Record<string, unknown> | null | undefined): HuumeState {
  if (!state) return { plans: {} }
  return {
    plans: (state.huume_plans as HuumePlans | undefined) ?? {},
    offer: state.huume_offer as HuumeOffer | undefined,
    action: state.huume_action as HuumeAction | undefined,
    legal: state.huume_legal as HuumeLegal | undefined,
    handbook: state.huume_handbook as HuumeHandbook | undefined,
  }
}

/** True when anything Huume-related is staged/tracked in this thread. */
export function hasHuumeContent(h: HuumeState): boolean {
  return Object.keys(h.plans).length > 0 || !!h.offer || !!h.action || !!h.legal
    || !!(h.handbook && h.handbook.pending_drafts?.length > 0)
}

export interface HuumePanelGateOpts {
  huumeMode: boolean
  state: Record<string, unknown> | null | undefined
  pdfUrl?: string | null
  agentMode?: boolean
}

/** Right-panel gate for the Huume card. Shows whenever huume content exists;
 * with huume mode on but nothing staged, only if it wouldn't displace the
 * PDF preview / AgentPanel — RightPanels suppresses both behind this flag,
 * so a bare huume thread must not cost an offer-letter its PDF. */
export function shouldShowHuumePanel(opts: HuumePanelGateOpts): boolean {
  if (!opts.huumeMode || !opts.state) return false
  return hasHuumeContent(getHuumeState(opts.state)) || (!opts.pdfUrl && !opts.agentMode)
}
