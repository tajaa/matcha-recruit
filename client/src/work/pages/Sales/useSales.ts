import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  campaignAction, createCampaign, deleteCampaign, deleteProspect, getCampaign, getCampaignStatus,
  getPlaybookOptions, importProspects, listCampaigns, listSalesWorkspaces, optOutProspect, resolveUnknown,
  sendBatch, updateCampaign, updateProspect,
} from '../../api/matchaWork/sales'
import type {
  CampaignAction, CampaignChanges, CampaignInput, ContactInput, PlaybookOptions, ProspectChanges,
  SalesCampaign, SalesCampaignDetail, SalesProspect, SalesWorkspace, WorkspaceCampaign,
} from '../../api/matchaWork/sales'
import { apiErrorText } from '../../utils/apiErrorText'

/** How often a sending campaign is checked (the Mac Pipeline's pace). */
export const POLL_MS = 15_000

/** Something is going out, or waiting to: worth polling. */
export function inFlight(detail: SalesCampaignDetail | null): boolean {
  if (!detail) return false
  const { counts, campaign } = detail
  return campaign.status === 'sending' || !!counts.approved || !!counts.claimed
}

type WorkspaceCampaigns = { projectId: string; campaigns: SalesCampaign[]; others: WorkspaceCampaign[] }

/**
 * The Sales page's data: the person's collab workspaces, their campaigns in
 * the chosen one, and the open campaign with its prospects. What is loaded is
 * tagged with the workspace or campaign it is for, so switching shows nothing
 * stale and a late answer for another one is never shown. While a batch is
 * out it polls the light status and reloads the full campaign only when a
 * message moved. Every write reports its error in `error` and resolves false.
 */
export function useSales(projectId: string | null, campaignId: string | null) {
  const [workspaces, setWorkspaces] = useState<SalesWorkspace[] | null>(null)
  const [options, setOptions] = useState<PlaybookOptions | null>(null)
  const [listed, setListed] = useState<WorkspaceCampaigns | null>(null)
  const [loaded, setLoaded] = useState<SalesCampaignDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const detail = loaded && loaded.campaign.id === campaignId ? loaded : null
  const own = listed && listed.projectId === projectId ? listed : null

  const openId = useRef(campaignId)
  const openProject = useRef(projectId)
  useLayoutEffect(() => {
    openId.current = campaignId
    openProject.current = projectId
  })

  useEffect(() => {
    let live = true
    Promise.all([listSalesWorkspaces(), getPlaybookOptions()])
      .then(([w, o]) => { if (live) { setWorkspaces(w.workspaces); setOptions(o) } })
      .catch((e) => { if (live) { setWorkspaces([]); setError(apiErrorText(e, "Couldn't load your workspaces.")) } })
    return () => { live = false }
  }, [])

  const loadCampaigns = useCallback((id: string) => listCampaigns(id).then(
    (out) => {
      if (openProject.current === id) setListed({ projectId: id, campaigns: out.campaigns, others: out.workspace_campaigns })
    },
    (e: unknown) => {
      if (openProject.current === id) setError(apiErrorText(e, "Couldn't load this workspace's campaigns."))
    },
  ), [])

  useEffect(() => { if (projectId) void loadCampaigns(projectId) }, [projectId, loadCampaigns])

  const loadDetail = useCallback((id: string) => getCampaign(id).then(
    (out) => { if (openId.current === id) setLoaded(out) },
    (e: unknown) => { if (openId.current === id) setError(apiErrorText(e, "Couldn't open this campaign.")) },
  ), [])

  useEffect(() => { if (campaignId) void loadDetail(campaignId) }, [campaignId, loadDetail])

  const sending = inFlight(detail)
  useEffect(() => {
    if (!sending || !detail) return
    const id = detail.campaign.id
    const before = new Map(detail.prospects.map((p) => [p.id, `${p.status}|${p.review_token}`]))
    const timer = setInterval(async () => {
      try {
        const status = await getCampaignStatus(id)
        const moved = status.campaign.status !== detail.campaign.status
          || status.prospects.some((p) => before.get(p.id) !== `${p.status}|${p.review_token}`)
        if (moved) await loadDetail(id)
      } catch {
        // A missed poll is retried on the next tick.
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [sending, detail, loadDetail])

  /** Runs a write, reloads what it changed, and says whether it worked. */
  const run = useCallback(async (fallback: string, write: () => Promise<unknown>, campaigns = false) => {
    const id = openId.current
    setBusy(true)
    setError(null)
    try {
      await write()
      await Promise.all([
        id ? loadDetail(id) : null,
        campaigns && openProject.current ? loadCampaigns(openProject.current) : null,
      ])
      return true
    } catch (e) {
      setError(apiErrorText(e, fallback))
      return false
    } finally {
      setBusy(false)
    }
  }, [loadCampaigns, loadDetail])

  const id = detail?.campaign.id ?? ''

  const create = useCallback(async (input: CampaignInput): Promise<SalesCampaign | null> => {
    if (!projectId) return null
    let made: SalesCampaign | null = null
    await run("Couldn't create the campaign.", async () => { made = await createCampaign(projectId, input) }, true)
    return made
  }, [projectId, run])

  return {
    workspaces, options, detail, busy, error, sending,
    campaigns: own?.campaigns ?? [],
    others: own?.others ?? [],
    clearError: () => setError(null),
    create,
    saveCampaign: (changes: CampaignChanges) =>
      run("Couldn't save the campaign.", () => updateCampaign(id, changes), true),
    /** Deletes the open campaign; the page then closes it. */
    remove: async () => {
      setBusy(true)
      setError(null)
      try {
        await deleteCampaign(id)
        if (openProject.current) await loadCampaigns(openProject.current)
        return true
      } catch (e) {
        setError(apiErrorText(e, "Couldn't delete the campaign."))
        return false
      } finally {
        setBusy(false)
      }
    },
    importContacts: async (contacts: ContactInput[]) => {
      let summary: Awaited<ReturnType<typeof importProspects>> | null = null
      const ok = await run("Couldn't import those contacts.", async () => { summary = await importProspects(id, contacts) })
      return ok ? summary : null
    },
    saveProspect: (prospect: SalesProspect, changes: ProspectChanges) =>
      run("Couldn't save this prospect.", () => updateProspect(id, prospect.id, changes)),
    optOut: (prospect: SalesProspect) =>
      run("Couldn't mark this person do not contact.", () => optOutProspect(id, prospect.id)),
    removeProspect: (prospect: SalesProspect) =>
      run("Couldn't delete this prospect.", () => deleteProspect(id, prospect.id)),
    resolve: (prospect: SalesProspect, outcome: 'sent' | 'not_sent') =>
      run("Couldn't record that.", () => resolveUnknown(id, prospect.id, outcome)),
    send: (sender: string, drafts: SalesProspect[], requestId: string) =>
      run("Couldn't approve this batch.", () =>
        sendBatch(id, sender, drafts.map((p) => ({ id: p.id, review_token: p.review_token })), requestId)),
    act: (action: CampaignAction) => run("Couldn't update the campaign.", () => campaignAction(id, action)),
  }
}

export type SalesState = ReturnType<typeof useSales>
