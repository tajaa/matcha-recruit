import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, Megaphone, Plus, Settings2, Sparkles } from 'lucide-react'
import type { AssistantDraftState } from './Assistant'
import type { ProspectStatus, SalesCampaign, SalesProspect } from '../api/matchaWork/sales'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import CampaignForm from './Sales/CampaignForm'
import ImportBox from './Sales/ImportBox'
import ProspectList from './Sales/ProspectList'
import ProspectPane from './Sales/ProspectPane'
import ReviewSend from './Sales/ReviewSend'
import { MAX_BATCH, STATUS_LABEL, assistantPrompt, footerProblem, orderProspects, sendable } from './Sales/salesLogic'
import { useSales, type SalesState } from './Sales/useSales'

/**
 * Sales campaigns on the web: the same campaigns as the Mac Pipeline. Pick a
 * workspace and a campaign; import contacts or have Espresso find and research
 * them; read each prospect and its draft; then review a batch exactly as it
 * will go out and send it from your own Gmail. Nothing is sent without that
 * review. URL: ?workspace=&campaign=&prospect=.
 */
export default function Sales() {
  const base = useWorkBase()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const projectId = params.get('workspace')
  const campaignId = params.get('campaign')
  const prospectId = params.get('prospect')
  const s = useSales(projectId, campaignId)
  const [creating, setCreating] = useState(false)

  function setParam(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next)
  }

  // One workspace: open it. A stale workspace in the URL is dropped.
  useEffect(() => {
    if (!s.workspaces) return
    if (projectId && !s.workspaces.some((w) => w.id === projectId)) setParam({ workspace: null, campaign: null, prospect: null })
    else if (!projectId && s.workspaces.length === 1) setParam({ workspace: s.workspaces[0].id })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the list or choice changes
  }, [s.workspaces, projectId])

  async function created(campaign: SalesCampaign | null) {
    if (!campaign) return
    setCreating(false)
    setParam({ campaign: campaign.id, prospect: null })
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className={`min-h-0 w-full shrink-0 flex-col border-r border-w-line bg-w-surface md:w-72 ${campaignId ? 'hidden md:flex' : 'flex'}`}>
        <div className="space-y-2 border-b border-w-line px-4 py-3">
          <h1 className="flex items-center gap-1.5 text-sm font-semibold text-w-text"><Megaphone size={14} />Sales</h1>
          {s.workspaces === null ? (
            <p className="flex items-center gap-1.5 text-[11px] text-w-dim"><Loader2 size={11} className="animate-spin" />Loading…</p>
          ) : s.workspaces.length === 0 ? (
            <p className="text-[11px] leading-4 text-w-dim">Campaigns live in a shared workspace. Create one from Home, then come back here.</p>
          ) : (
            <select aria-label="Workspace" value={projectId ?? ''}
              onChange={(e) => setParam({ workspace: e.target.value || null, campaign: null, prospect: null })}
              className="w-full rounded-md border border-w-line bg-w-surface2/50 px-2 py-1 text-xs text-w-text">
              <option value="">Choose a workspace</option>
              {s.workspaces.map((w) => <option key={w.id} value={w.id}>{w.title}</option>)}
            </select>
          )}
          {projectId && (
            <button type="button" onClick={() => { setCreating(true); setParam({ campaign: null, prospect: null }) }}
              className="flex items-center gap-1 text-[11px] font-semibold text-w-accent hover:underline">
              <Plus size={12} />New campaign
            </button>
          )}
        </div>
        <nav aria-label="Campaigns" className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
          {s.campaigns.map((c) => (
            <button key={c.id} type="button" onClick={() => { setCreating(false); setParam({ campaign: c.id, prospect: null }) }}
              className={`block w-full rounded-md px-2.5 py-1.5 text-left ${c.id === campaignId ? 'bg-w-surface2 text-w-text' : 'text-w-dim hover:bg-w-surface2/50'}`}>
              <span className="block truncate text-xs font-semibold">{c.title}</span>
              <span className="block text-[10px] text-w-faint">
                {[c.playbook === 'consulting' ? 'Consulting' : '', c.status === 'sending' ? 'Sending' : c.status === 'paused' ? 'Paused' : ''].filter(Boolean).join(' · ') || 'Campaign'}
              </span>
            </button>
          ))}
          {s.others.length > 0 && (
            <div className="pt-3">
              <p className="px-2.5 text-[10px] font-semibold uppercase tracking-wider text-w-faint">Other people's campaigns here</p>
              {s.others.map((o) => (
                <p key={o.id} className="px-2.5 py-1 text-[11px] text-w-dim">
                  {o.title} · {o.creator} · {o.sent}/{o.prospects} sent
                </p>
              ))}
            </div>
          )}
        </nav>
      </aside>

      <main className={`min-h-0 min-w-0 flex-1 overflow-y-auto ${campaignId || creating ? 'block' : 'hidden md:block'}`}>
        {s.error && (
          <p role="alert" className="mx-4 mt-3 flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-400">
            <span className="flex-1">{s.error}</span>
            <button type="button" onClick={s.clearError} className="text-[11px] underline">Dismiss</button>
          </p>
        )}
        {creating && projectId ? (
          <div className="max-w-xl p-4">
            <h2 className="mb-3 text-sm font-semibold text-w-text">New campaign</h2>
            <CampaignForm house={s.options?.house ?? null} busy={s.busy}
              onSave={async (input) => created(await s.create(input))} onCancel={() => setCreating(false)} />
          </div>
        ) : !campaignId ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
            <Megaphone size={28} className="text-w-faint" />
            <p className="text-sm font-semibold text-w-text">Open a campaign on the left</p>
            <p className="max-w-sm text-xs text-w-dim">
              Import contacts or have Espresso find them, read each draft, then review a batch and send it from your Gmail.
            </p>
          </div>
        ) : !s.detail ? (
          <p className="flex items-center gap-1.5 p-4 text-xs text-w-dim"><Loader2 size={12} className="animate-spin" />Loading the campaign…</p>
        ) : (
          <CampaignView
            key={campaignId}
            s={s}
            prospectId={prospectId}
            onOpenProspect={(id) => setParam({ prospect: id })}
            onClose={() => setParam({ campaign: null, prospect: null })}
            onAskEspresso={(campaign) => {
              const state: AssistantDraftState = { draft: { id: Date.now(), text: assistantPrompt(campaign) } }
              navigate(`${base}/assistant`, { state })
            }}
            connectionsPath={`${base}/connections`}
          />
        )}
      </main>

    </div>
  )
}

/**
 * The open campaign: its header and actions, settings, import, the prospects
 * (ticked drafts make a batch) and the open prospect. Keyed by campaign, so
 * the selection and open panels start fresh for each one.
 */
function CampaignView({ s, prospectId, onOpenProspect, onClose, onAskEspresso, connectionsPath }: {
  s: SalesState
  prospectId: string | null
  onOpenProspect: (id: string | null) => void
  onClose: () => void
  onAskEspresso: (campaign: SalesCampaign) => void
  connectionsPath: string
}) {
  const detail = s.detail!
  const [editing, setEditing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const consulting = detail.campaign.playbook === 'consulting'
  const prospects = useMemo(() => orderProspects(detail.prospects, consulting), [detail, consulting])
  const open = prospects.find((p) => p.id === prospectId) ?? null
  // A selection only ever holds drafts that are still ready.
  const chosen = prospects.filter((p) => selected.has(p.id) && sendable(p))
  const readyCount = prospects.filter(sendable).length

  function toggle(p: SalesProspect) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(p.id)) next.delete(p.id)
      else if (next.size < MAX_BATCH) next.add(p.id)
      return next
    })
  }

  async function removeCampaign() {
    if (!window.confirm(`Delete "${detail.campaign.title}" and its prospects? Do-not-contact entries are kept.`)) return
    if (await s.remove()) onClose()
  }

  async function approve(sender: string, requestId: string) {
    const ok = await s.send(sender, chosen, requestId)
    if (ok) { setReviewing(false); setSelected(new Set()) }
    return ok
  }

  return (
    <div className="flex min-h-full flex-col lg:flex-row">
      <div className="min-w-0 flex-1 space-y-4 p-4">
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={onClose} className="text-[11px] text-w-dim md:hidden">← Campaigns</button>
            <h2 className="text-sm font-semibold text-w-text">{detail.campaign.title}</h2>
            {consulting && <span className="rounded bg-w-accent/10 px-1.5 py-0.5 text-[10px] font-semibold text-w-accent">Consulting</span>}
            <button type="button" onClick={() => setEditing((v) => !v)} aria-label="Campaign settings"
              className="ml-auto rounded p-1 text-w-dim hover:bg-w-surface2"><Settings2 size={14} /></button>
          </div>
          <p className="text-[11px] text-w-dim">
            {Object.entries(detail.counts).filter(([, n]) => n)
              .map(([k, n]) => `${n} ${STATUS_LABEL[k as ProspectStatus].toLowerCase()}`).join(' · ') || 'No prospects yet'}
          </p>
          {detail.campaign.error && <p className="text-[11px] text-red-400">{detail.campaign.error}</p>}
          {footerProblem(detail.campaign.footer) && (
            <p className="text-[11px] text-amber-400">Add a footer in settings (how to opt out, and your postal address) before sending.</p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => onAskEspresso(detail.campaign)}
              className="inline-flex items-center gap-1 rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white">
              <Sparkles size={12} />Research and draft with Espresso
            </button>
            <button type="button" onClick={() => setImporting((v) => !v)}
              className="rounded-md border border-w-line px-3 py-1.5 text-xs font-semibold text-w-text hover:bg-w-surface2">Import</button>
            {s.sending && (
              <span className="inline-flex items-center gap-1 text-[11px] text-w-dim"><Loader2 size={11} className="animate-spin" />Sending</span>
            )}
            {detail.campaign.status === 'sending' && (
              <button type="button" disabled={s.busy} onClick={() => void s.act('pause')} className="text-[11px] text-w-dim hover:text-w-text">Pause</button>
            )}
            {detail.campaign.status === 'paused' && !!detail.counts.approved && (
              <>
                <button type="button" disabled={s.busy} onClick={() => void s.act('resume')} className="text-[11px] font-semibold text-w-accent hover:underline">Resume</button>
                <button type="button" disabled={s.busy} onClick={() => void s.act('release_pending')} className="text-[11px] text-w-dim hover:text-w-text">Release pending drafts</button>
              </>
            )}
            {!!detail.counts.failed && (
              <button type="button" disabled={s.busy} onClick={() => void s.act('retry_failed')} className="text-[11px] text-w-dim hover:text-w-text">Review failed again</button>
            )}
          </div>
        </header>

        {editing && (
          <div className="rounded-lg border border-w-line p-3">
            <CampaignForm key={detail.campaign.updated_at} campaign={detail.campaign} house={null} busy={s.busy}
              onSave={async (input) => { if (await s.saveCampaign(input)) setEditing(false) }} onCancel={() => setEditing(false)} />
            <button type="button" disabled={s.busy} onClick={() => void removeCampaign()}
              className="mt-3 text-[11px] text-red-400 hover:underline">Delete campaign</button>
          </div>
        )}
        {importing && (
          <div className="rounded-lg border border-w-line p-3">
            <ImportBox busy={s.busy} onImport={s.importContacts} />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[11px] text-w-dim">{chosen.length ? `${chosen.length} selected` : `${readyCount} ready to send`}</p>
          {readyCount > 0 && !chosen.length && (
            <button type="button" onClick={() => setSelected(new Set(prospects.filter(sendable).slice(0, MAX_BATCH).map((p) => p.id)))}
              className="text-[11px] text-w-accent hover:underline">
              Select {Math.min(readyCount, MAX_BATCH)}
            </button>
          )}
          {chosen.length > 0 && (
            <>
              <button type="button" onClick={() => setSelected(new Set())} className="text-[11px] text-w-dim hover:text-w-text">Clear</button>
              <button type="button" disabled={s.sending} onClick={() => setReviewing(true)}
                className="ml-auto rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
                Review and send {chosen.length}
              </button>
            </>
          )}
        </div>
        <ProspectList prospects={prospects} consulting={consulting} selected={selected} openId={prospectId}
          onToggle={toggle} onOpen={(p) => onOpenProspect(p.id)} />
      </div>

      {open && (
        <aside className="border-t border-w-line lg:w-[420px] lg:shrink-0 lg:border-l lg:border-t-0">
          <ProspectPane
            key={`${open.id}:${open.review_token}:${open.status}`}
            prospect={open}
            footer={detail.campaign.footer}
            busy={s.busy}
            onSave={(changes) => s.saveProspect(open, changes)}
            onOptOut={() => s.optOut(open)}
            onDelete={async () => { const ok = await s.removeProspect(open); if (ok) onOpenProspect(null); return ok }}
            onResolve={(outcome) => s.resolve(open, outcome)}
            onClose={() => onOpenProspect(null)}
          />
        </aside>
      )}

      {reviewing && (
        <ReviewSend drafts={chosen} footer={detail.campaign.footer} busy={s.busy}
          connectionsPath={connectionsPath} onApprove={approve} onClose={() => setReviewing(false)} />
      )}
    </div>
  )
}
