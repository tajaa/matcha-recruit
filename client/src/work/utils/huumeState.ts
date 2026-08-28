import type {
  HuumeAction, HuumeActionSendOffer, HuumeHandbook, HuumeLegal, HuumeOffer, HuumePlan, HuumePlans, HuumeRecordRef,
} from '../types'

export interface HuumeState {
  plans: HuumePlans
  offer?: HuumeOffer
  action?: HuumeAction
  legal?: HuumeLegal
  handbook?: HuumeHandbook
  /** The panel's open-record working set — accumulates across turns (see
   * `merge_open_records` server-side) rather than replacing on each
   * show_record call, so asking Huume to show three things in a row keeps
   * all three tabs open instead of only the last one. Optional (like the
   * other Huume state slices) — `getHuumeState` always fills it in as `[]`
   * when absent; test-constructed states may simply omit it. */
  records?: HuumeRecordRef[]
}

/** The one place `current_state`'s untyped Huume keys get cast. The server
 * owns these shapes (services/huume/ writes them); an absent key just means
 * the feature hasn't been used in this thread yet. */
export function getHuumeState(state: Record<string, unknown> | null | undefined): HuumeState {
  if (!state) return { plans: {}, records: [] }
  const rawRecords = state.huume_records
  return {
    plans: (state.huume_plans as HuumePlans | undefined) ?? {},
    offer: state.huume_offer as HuumeOffer | undefined,
    action: state.huume_action as HuumeAction | undefined,
    legal: state.huume_legal as HuumeLegal | undefined,
    handbook: state.huume_handbook as HuumeHandbook | undefined,
    records: Array.isArray(rawRecords) ? (rawRecords as HuumeRecordRef[]) : [],
  }
}

/** True when anything Huume-related is staged/tracked in this thread. */
export function hasHuumeContent(h: HuumeState): boolean {
  return Object.keys(h.plans).length > 0 || !!h.offer || !!h.action || !!h.legal || (h.records?.length ?? 0) > 0
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

// ──────────────────────────────────────────────────────────────────────
// Artifact model — what the right panel actually renders as tabs/documents.
// ──────────────────────────────────────────────────────────────────────

export type HuumeArtifact =
  | { kind: 'offer'; key: string; offerId: string; label?: string }
  | { kind: 'plan'; key: string; offerId: string; plan: HuumePlan }
  | { kind: 'action'; key: string; action: Exclude<HuumeAction, HuumeActionSendOffer> }
  | { kind: 'handbook'; key: string; sessionId: string; pendingDrafts: HuumeHandbook['pending_drafts'] }
  | { kind: 'legal'; key: string; matterId: string; title?: string | null }
  | { kind: 'record'; key: string; recordType: string; recordId: string; label?: string | null }

/** Ordered artifact list for the right panel's tabs.
 * Order: offer(s), one per plan (state-key order), the staged non-offer
 * action (if any), handbook, legal. `key` is `${kind}:${id}` — stable tab
 * identity across state updates.
 *
 * The offer artifact is synthesized from a staged `send_offer` action when
 * `huume_offer` hasn't been written yet (drafting happens before the offer
 * row necessarily has state here) — deduped when both name the same id. A
 * staged `send_offer` for a DIFFERENT offer than the last-drafted one (e.g.
 * draft A → send A → draft B → send_offer(offer_id=A) again) gets its own
 * artifact rather than being silently dropped — otherwise the panel would
 * render B's letter while the chat strip confirms sending A. */
export function deriveHuumeArtifacts(h: HuumeState): HuumeArtifact[] {
  const artifacts: HuumeArtifact[] = []

  const offerIds = new Set<string>()
  if (h.offer?.offer_id) offerIds.add(h.offer.offer_id)
  if (h.action?.type === 'send_offer') offerIds.add(h.action.offer_id)
  for (const offerId of offerIds) artifacts.push({ kind: 'offer', key: `offer:${offerId}`, offerId })

  for (const [planOfferId, plan] of Object.entries(h.plans)) {
    artifacts.push({ kind: 'plan', key: `plan:${planOfferId}`, offerId: planOfferId, plan })
  }

  if (h.action && h.action.type !== 'send_offer' && h.action.status !== 'cancelled') {
    const idKey =
      h.action.type === 'discipline_draft' ? h.action.confirm_id
      : h.action.type === 'ir_report' ? h.action.confirm_id
      : h.action.type === 'er_case' ? h.action.confirm_id
      : h.action.type === 'training_assign' ? h.action.requirement_id
      : h.action.type === 'amend_handbook' ? h.action.target_handbook_id
      : h.action.type === 'pto_decision' ? h.action.request_id
      : h.action.type === 'discipline_from_incident' ? h.action.confirm_id
      : h.action.type === 'discipline_decision' ? h.action.record_id
      : h.action.type === 'ems_promote' ? h.action.event_id
      : h.action.type === 'inventory_movement' ? h.action.confirm_id
      : h.action.type === 'inventory_order_decision' ? h.action.order_id
      : h.action.type === 'inventory_item_create' ? h.action.confirm_id
      : h.action.type === 'inventory_item_archive' ? h.action.item_id
      : h.action.type === 'inventory_receipt' ? h.action.confirm_id
      : h.action.type === 'schedule_change' ? h.action.confirm_id
      : h.action.type === 'schedule_week_draft' ? h.action.confirm_id
      : h.action.type === 'schedule_note' ? h.action.confirm_id
      : h.action.type === 'meal_break_waiver' ? h.action.confirm_id
      : h.action.type === 'work_permit' ? h.action.confirm_id
      : h.action.type === 'eligibility_case_decision' ? h.action.confirm_id
      : ((): never => { throw new Error('unreachable') })()
    artifacts.push({ kind: 'action', key: `action:${h.action.type}:${idKey}`, action: h.action })
  }

  if (h.handbook && h.handbook.pending_drafts?.length > 0) {
    artifacts.push({
      kind: 'handbook', key: `handbook:${h.handbook.session_id}`,
      sessionId: h.handbook.session_id, pendingDrafts: h.handbook.pending_drafts,
    })
  }

  if (h.legal) {
    artifacts.push({ kind: 'legal', key: `legal:${h.legal.matter_id}`, matterId: h.legal.matter_id, title: h.legal.title })
  }

  for (const record of h.records ?? []) {
    artifacts.push({
      kind: 'record', key: `record:${record.record_type}:${record.record_id}`,
      recordType: record.record_type, recordId: record.record_id, label: record.label,
    })
  }

  return artifacts
}

/** Which tab should be selected by default: the artifact owning a
 * `status === 'proposed'` action (the offer artifact for a staged
 * `send_offer`, the action artifact otherwise), else the first artifact,
 * else null when there's nothing to show. */
export function defaultArtifactKey(artifacts: HuumeArtifact[], action?: HuumeAction): string | null {
  if (action?.status === 'proposed') {
    if (action.type === 'send_offer') {
      const offerArtifact = artifacts.find((a) => a.kind === 'offer' && a.offerId === action.offer_id)
      if (offerArtifact) return offerArtifact.key
    } else {
      const actionArtifact = artifacts.find((a) => a.kind === 'action')
      if (actionArtifact) return actionArtifact.key
    }
  }
  return artifacts[0]?.key ?? null
}
