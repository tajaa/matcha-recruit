import { useCallback, useEffect, useRef, useState } from 'react'
import { Search, Loader2, Globe, Check, CircleAlert, ExternalLink, Server, RefreshCw, LogOut, ShieldCheck } from 'lucide-react'
import { cappeApi } from '../api'
import DnsRecordsModal from './DnsRecordsModal'
import type {
  CappeDomain,
  CappeDomainConfig,
  CappeDomainEdgeStatus,
  CappeDomainSearchResult,
} from '../types'

const input =
  'rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500'

const STATUS_STYLE: Record<CappeDomain['status'], string> = {
  active: 'bg-emerald-500/15 text-emerald-300',
  registering: 'bg-amber-500/15 text-amber-300',
  pending: 'bg-zinc-700/40 text-zinc-300',
  failed: 'bg-red-500/15 text-red-300',
  expired: 'bg-zinc-700/40 text-zinc-400',
  transfer_requested: 'bg-zinc-700/40 text-zinc-300',
}

/** Certificate/edge progress, shown next to the registration status: a domain
 *  is paid for and 'active' well before its certificate exists. */
const EDGE_LABEL: Record<CappeDomainEdgeStatus, string> = {
  none: '',
  provisioning: 'securing…',
  pending_dns: 'waiting for DNS',
  live: 'secured',
  failed: 'setup failed',
}
const EDGE_STYLE: Record<CappeDomainEdgeStatus, string> = {
  none: '',
  provisioning: 'bg-amber-500/15 text-amber-300',
  pending_dns: 'bg-sky-500/15 text-sky-300',
  live: 'bg-emerald-500/15 text-emerald-300',
  failed: 'bg-red-500/15 text-red-300',
}

/** Anything still moving on its own — poll while one of these is on screen. */
const settling = (d: CappeDomain) =>
  d.status === 'registering' || d.edge_status === 'provisioning' || d.edge_status === 'pending_dns'

const money = (cents: number | null) => (cents == null ? '' : `$${(cents / 100).toFixed(2)}/yr`)

/** Buy a new domain (Porkbun, charged via Stripe) or connect one you already
 *  own, plus the list of this site's domains with live registration status. */
export default function DomainManager({ siteId }: { siteId: string }) {
  const [domains, setDomains] = useState<CappeDomain[] | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CappeDomainSearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [buying, setBuying] = useState<string | null>(null)
  const [connect, setConnect] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [verifying, setVerifying] = useState<string | null>(null)
  const [dnsFor, setDnsFor] = useState<CappeDomain | null>(null)
  const [acting, setActing] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [config, setConfig] = useState<CappeDomainConfig | null>(null)

  const loadDomains = useCallback(() => {
    cappeApi.get<CappeDomain[]>(`/domains?site_id=${siteId}`).then(setDomains).catch(() => setDomains([]))
  }, [siteId])
  useEffect(loadDomains, [loadDomains])

  useEffect(() => {
    cappeApi
      .get<CappeDomainConfig>('/domains/config')
      .then(setConfig)
      .catch(() => setConfig({ enabled: false, routing_endpoint: null }))
  }, [])

  // Poll while anything is still settling — the Stripe webhook, the registrar
  // call and the CloudFront certificate all land asynchronously.
  //
  // The interval is keyed on the SITE, never on `domains`: depending on the list
  // tore the timer down and rebuilt it on every refresh, so the 5s tick restarted
  // from zero each time instead of firing. The current list is read through a ref.
  const domainsRef = useRef<CappeDomain[] | null>(null)
  useEffect(() => {
    domainsRef.current = domains
  }, [domains])
  useEffect(() => {
    const t = setInterval(() => {
      if (domainsRef.current?.some(settling)) loadDomains()
    }, 5000)
    return () => clearInterval(t)
  }, [loadDomains])

  async function search() {
    const q = query.trim()
    if (!q) return
    setSearching(true); setError(null); setResults(null)
    try {
      setResults(await cappeApi.get<CappeDomainSearchResult[]>(`/domains/search?q=${encodeURIComponent(q)}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  async function buy(domain: string) {
    setBuying(domain); setError(null)
    try {
      const res = await cappeApi.post<{ domain_id: string; checkout_url: string }>('/domains/purchase', {
        site_id: siteId,
        domain,
      })
      // Hand off to Stripe Checkout; registration finishes via the webhook.
      window.location.href = res.checkout_url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start checkout')
      setBuying(null)
    }
  }

  async function connectOwn() {
    const d = connect.trim()
    if (!d) return
    setConnecting(true); setError(null)
    try {
      // Returns a PENDING claim + a TXT token; surfaced in "Your domains" below
      // with the record to add and a Verify button.
      await cappeApi.post<CappeDomain>('/domains/connect', { site_id: siteId, domain: d })
      setConnect('')
      loadDomains()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not connect domain')
    } finally {
      setConnecting(false)
    }
  }

  async function verify(id: string) {
    setVerifying(id); setError(null)
    try {
      await cappeApi.post<CappeDomain>(`/domains/${id}/verify`)
      loadDomains()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verification failed')
    } finally {
      setVerifying(null)
    }
  }

  async function toggleAutoRenew(d: CappeDomain) {
    setActing(d.id); setError(null)
    try {
      await cappeApi.patch<CappeDomain>(`/domains/${d.id}/auto-renew`, { auto_renew: !d.auto_renew })
      loadDomains()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update auto-renew')
    } finally {
      setActing(null)
    }
  }

  async function retryEdge(d: CappeDomain) {
    setActing(d.id); setError(null)
    try {
      await cappeApi.post<CappeDomain>(`/domains/${d.id}/edge/retry`)
      loadDomains()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not retry setup')
    } finally {
      setActing(null)
    }
  }

  async function requestTransfer(d: CappeDomain) {
    if (!confirm(`Request to transfer ${d.domain} to another registrar? We'll email you the authorization code.`)) return
    setActing(d.id); setError(null)
    try {
      await cappeApi.post<CappeDomain>(`/domains/${d.id}/transfer-request`)
      loadDomains()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not request transfer')
    } finally {
      setActing(null)
    }
  }

  if (config && !config.enabled) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
          <Globe className="h-4 w-4 text-zinc-500" /> Custom domains are coming soon
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          Your site is live at its <span className="text-zinc-300">.gummfit.com</span> address in the
          meantime. We'll turn on buying and connecting your own domain — with the certificate handled
          for you — shortly.
        </p>
      </div>
    )
  }

  const endpoint = config?.routing_endpoint

  return (
    <div className="space-y-5">
      <div>
        <label className="mb-1 block text-sm font-medium text-zinc-300">Find a domain to buy</label>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder="yourbrand  or  yourbrand.com"
            className={`flex-1 ${input}`}
          />
          <button
            onClick={search}
            disabled={searching}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Search
          </button>
        </div>

        {results && (
          <ul className="mt-3 space-y-1.5">
            {results.length === 0 && <li className="text-sm text-zinc-500">No results.</li>}
            {results.map((r) => (
              <li
                key={r.domain}
                className="flex items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2"
              >
                <span className="flex items-center gap-2 text-sm text-zinc-200">
                  <Globe className="h-4 w-4 text-zinc-500" /> {r.domain}
                </span>
                {r.available ? (
                  <button
                    onClick={() => buy(r.domain)}
                    disabled={buying === r.domain}
                    className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-60"
                  >
                    {buying === r.domain ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                    Buy {money(r.price_cents)}
                  </button>
                ) : (
                  <span className="text-xs text-zinc-500">Taken</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-zinc-800 pt-4">
        <label className="mb-1 block text-sm font-medium text-zinc-300">Already own a domain? Connect it</label>
        <div className="flex gap-2">
          <input
            value={connect}
            onChange={(e) => setConnect(e.target.value)}
            placeholder="www.yourdomain.com"
            className={`flex-1 ${input}`}
          />
          <button
            onClick={connectOwn}
            disabled={connecting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-60"
          >
            {connecting ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Connect
          </button>
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          Connect it here first — we'll verify you own it, then show the record to add. You'll point an{' '}
          <span className="text-zinc-300">ALIAS</span>/<span className="text-zinc-300">ANAME</span> record on
          the apex (or a <span className="text-zinc-300">CNAME</span> on www) at{' '}
          {endpoint ? (
            <span className="break-all font-mono text-zinc-300">{endpoint}</span>
          ) : (
            'the address we give you'
          )}
          . The SSL certificate is issued and renewed for you.
        </p>
      </div>

      {error && (
        <p className="flex items-center gap-1.5 text-sm text-red-400">
          <CircleAlert className="h-4 w-4" /> {error}
        </p>
      )}

      {domains && domains.length > 0 && (
        <div className="border-t border-zinc-800 pt-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Your domains</div>
          <ul className="space-y-1.5">
            {domains.map((d) => (
              <li key={d.id} className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-sm text-zinc-200">
                    {d.status === 'active' ? (
                      <Check className="h-4 w-4 text-emerald-400" />
                    ) : d.status === 'registering' ? (
                      <Loader2 className="h-4 w-4 animate-spin text-amber-400" />
                    ) : (
                      <Globe className="h-4 w-4 text-zinc-500" />
                    )}
                    <a href={`https://${d.domain}`} target="_blank" rel="noreferrer" className="hover:underline">
                      {d.domain}
                    </a>
                    {d.status === 'active' && <ExternalLink className="h-3 w-3 text-zinc-500" />}
                  </span>
                  <div className="flex items-center gap-2">
                    {d.kind === 'connect' && d.status === 'pending' && (
                      <button
                        onClick={() => verify(d.id)}
                        disabled={verifying === d.id}
                        className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-60"
                      >
                        {verifying === d.id ? <Loader2 className="h-3 w-3 animate-spin" /> : null} Verify
                      </button>
                    )}
                    {d.kind === 'register' && d.status === 'active' && (
                      <>
                        <button
                          onClick={() => setDnsFor(d)}
                          title="Manage DNS records"
                          className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-800"
                        >
                          <Server className="h-3 w-3" /> DNS
                        </button>
                        <button
                          onClick={() => toggleAutoRenew(d)}
                          disabled={acting === d.id}
                          title={d.auto_renew ? 'Auto-renew on — click to turn off' : 'Auto-renew off — click to turn on'}
                          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs disabled:opacity-60 ${
                            d.auto_renew
                              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                              : 'border-zinc-700 text-zinc-400'
                          }`}
                        >
                          <RefreshCw className="h-3 w-3" /> {d.auto_renew ? 'Auto-renew' : 'Renew off'}
                        </button>
                        <button
                          onClick={() => requestTransfer(d)}
                          disabled={acting === d.id || !!d.transfer_requested_at}
                          title="Transfer this domain to another registrar"
                          className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
                        >
                          <LogOut className="h-3 w-3" /> {d.transfer_requested_at ? 'Transfer requested' : 'Transfer out'}
                        </button>
                      </>
                    )}
                    {d.edge_status === 'failed' && (
                      <button
                        onClick={() => retryEdge(d)}
                        disabled={acting === d.id}
                        title="Retry certificate setup"
                        className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
                      >
                        <RefreshCw className="h-3 w-3" /> Retry setup
                      </button>
                    )}
                    {d.edge_status !== 'none' && (
                      <span
                        title={d.edge_error || undefined}
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${EDGE_STYLE[d.edge_status]}`}
                      >
                        <ShieldCheck className="h-3 w-3" /> {EDGE_LABEL[d.edge_status]}
                      </span>
                    )}
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[d.status]}`}>
                      {d.status === 'registering'
                        ? 'setting up…'
                        : d.status === 'transfer_requested'
                          ? 'transferring out'
                          : d.status}
                    </span>
                  </div>
                </div>
                {d.edge_status === 'pending_dns' && (d.cf_routing_endpoint || endpoint) && (
                  <div className="mt-2 rounded-md bg-zinc-900 p-2 text-xs text-zinc-400">
                    Point the domain at us, then this turns green on its own (it can take up to an hour):
                    <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px] text-zinc-300">
                      <span className="text-zinc-500">ALIAS / ANAME</span>
                      <span className="break-all">{d.domain} → {d.cf_routing_endpoint || endpoint}</span>
                      <span className="text-zinc-500">CNAME</span>
                      <span className="break-all">www.{d.domain} → {d.cf_routing_endpoint || endpoint}</span>
                    </div>
                  </div>
                )}
                {d.edge_status === 'failed' && d.edge_error && (
                  <p className="mt-2 text-xs text-red-400">{d.edge_error}</p>
                )}
                {d.kind === 'connect' && d.status === 'pending' && d.verification_token && (
                  <div className="mt-2 rounded-md bg-zinc-900 p-2 text-xs text-zinc-400">
                    Add this DNS <span className="font-medium text-zinc-300">TXT</span> record at your registrar,
                    then click Verify:
                    <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px] text-zinc-300">
                      <span className="text-zinc-500">host</span>
                      <span className="break-all">_cappe-verify.{d.domain}</span>
                      <span className="text-zinc-500">value</span>
                      <span className="break-all">{d.verification_token}</span>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {dnsFor && <DnsRecordsModal domainId={dnsFor.id} domain={dnsFor.domain} onClose={() => setDnsFor(null)} />}
    </div>
  )
}
