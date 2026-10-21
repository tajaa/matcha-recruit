import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { cappeApi } from '../../../api'
import SurfaceShell from '../../../components/SurfaceShell'
import type { CappeSocialConnection, CappeSocialConnections, CappeSocialOverview, CappeSocialSettings } from '../../../types'
import Composer from './Composer'
import Inbox from './Inbox'
import Queue from './Queue'
import Setup from './Setup'

type Tab = 'create' | 'queue' | 'inbox' | 'setup'

// Social growth: drop photos → caption (optionally with AI) → schedule to the
// connected Instagram / Facebook accounts; the inbox answers comments and DMs.
// Server side: server/app/cappe/routes/social.py (+ services/social/).
export default function Social() {
  const { siteId = '' } = useParams<{ siteId: string }>()
  const [params, setParams] = useSearchParams()
  const [notice, setNotice] = useState<{ tone: 'ok' | 'err'; text: string } | null>(() => {
    const connected = params.get('connected')
    const failed = params.get('social_error')
    if (failed) return { tone: 'err', text: `Couldn’t connect: ${failed}` }
    if (connected) return { tone: 'ok', text: `Connected ${connected.split(',').join(' and ')}.` }
    return null
  })
  const [tab, setTab] = useState<Tab | null>(() => (params.get('connected') || params.get('social_error') ? 'setup' : null))
  const [overview, setOverview] = useState<CappeSocialOverview | null>(null)
  const [connections, setConnections] = useState<CappeSocialConnection[] | null>(null)
  const [configured, setConfigured] = useState(false)
  const [settings, setSettings] = useState<CappeSocialSettings | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // The OAuth round-trip lands here with ?connected= / ?social_error=; show it
  // once and take it off the URL so a reload doesn't repeat it.
  useEffect(() => {
    if (params.get('connected') || params.get('social_error')) setParams({}, { replace: true })
  }, [params, setParams])

  useEffect(() => {
    let live = true
    Promise.all([
      cappeApi.get<CappeSocialConnections>(`/sites/${siteId}/social/connections`),
      cappeApi.get<CappeSocialSettings>(`/sites/${siteId}/social/settings`),
    ]).then(([conns, s]) => {
      if (!live) return
      setConnections(conns.connections)
      setConfigured(conns.configured)
      setSettings(s)
      setTab((t) => t ?? (conns.connections.length ? 'create' : 'setup'))
    }).catch((e) => { if (live) setLoadError(e instanceof Error ? e.message : 'Couldn’t load Social') })
    return () => { live = false }
  }, [siteId])

  useEffect(() => {
    cappeApi.get<CappeSocialOverview>(`/sites/${siteId}/social/overview`).then(setOverview).catch(() => setOverview(null))
  }, [siteId, refreshKey])

  function posted(message: string) {
    setNotice({ tone: 'ok', text: message })
    setRefreshKey((n) => n + 1)
    setTab('queue')
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'create', label: 'Create' },
    { key: 'queue', label: 'Queue', count: overview?.scheduled },
    { key: 'inbox', label: 'Inbox', count: overview ? overview.inbox_new + overview.drafts_waiting : undefined },
    { key: 'setup', label: 'Accounts & AI' },
  ]

  return (
    <SurfaceShell title="Social" subtitle="Post to Instagram and Facebook, schedule ahead, and answer comments and messages.">
      {notice && (
        <div role="status" className={`mb-4 flex items-start justify-between gap-3 rounded-xl border px-4 py-3 text-sm ${notice.tone === 'ok'
          ? 'border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-300' : 'border-red-500/30 bg-red-500/[0.06] text-red-300'}`}>
          {notice.text}
          <button type="button" onClick={() => setNotice(null)} className="text-xs opacity-70 hover:opacity-100">Dismiss</button>
        </div>
      )}
      {overview && (
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Scheduled" value={overview.scheduled} />
          <Stat label="Posted (30 days)" value={overview.published_30d} />
          <Stat label="Waiting on you" value={overview.inbox_new + overview.drafts_waiting} />
          <Stat label="Followers" value={overview.followers.reduce((n, f) => n + (f.followers_count ?? 0), 0)}
            hint={overview.followers.length ? overview.followers.map((f) => `${f.platform}: ${f.followers_count ?? '—'}`).join(' · ') : 'No accounts yet'} />
        </div>
      )}
      {loadError ? (
        <p role="alert" className="text-sm text-red-400">{loadError}</p>
      ) : connections === null || tab === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : (
        <>
          <div className="mb-5 flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
            {tabs.map((t) => (
              <button key={t.key} type="button" onClick={() => setTab(t.key)}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium ${tab === t.key
                  ? 'bg-lime-400 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>
                {t.label}{t.count ? <span className="ml-1 opacity-70">{t.count}</span> : null}
              </button>
            ))}
          </div>
          {tab === 'create' && (
            <Composer siteId={siteId} connections={connections} settings={settings} metaConfigured={configured} onPosted={posted} />
          )}
          {tab === 'queue' && <Queue siteId={siteId} refreshKey={refreshKey} />}
          {tab === 'inbox' && <Inbox siteId={siteId} settings={settings} />}
          {tab === 'setup' && (
            <Setup siteId={siteId} configured={configured} connections={connections} settings={settings}
              onConnections={(list) => { setConnections(list); setRefreshKey((n) => n + 1) }} onSettings={setSettings} />
          )}
        </>
      )}
    </SurfaceShell>
  )
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3" title={hint}>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-0.5 text-xl font-semibold text-zinc-50">{value.toLocaleString()}</div>
    </div>
  )
}
