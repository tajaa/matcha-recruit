import { useCallback, useEffect, useState } from 'react'
import { Search, Loader2, Globe, Check, CircleAlert, ExternalLink, Server, RefreshCw, LogOut } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import DnsRecordsModal from './DnsRecordsModal'
import type { CappeDomain, CappeDomainSearchResult } from '../../types/cappe'

const input =
  'rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500'

const STATUS_STYLE: Record<CappeDomain['status'], string> = {
  active: 'bg-emerald-500/15 text-emerald-300',
  registering: 'bg-amber-500/15 text-amber-300',
  pending: 'bg-zinc-700/40 text-zinc-300',
  failed: 'bg-red-500/15 text-red-300',
  expired: 'bg-zinc-700/40 text-zinc-400',
}

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

  const loadDomains = useCallback(() => {
    cappeApi.get<CappeDomain[]>(`/domains?site_id=${siteId}`).then(setDomains).catch(() => setDomains([]))
  }, [siteId])
  useEffect(loadDomains, [loadDomains])

  // Poll while any domain is still registering (the webhook + finalizer run async).
  useEffect(() => {
    if (!domains?.some((d) => d.status === 'registering')) return
    const t = setInterval(loadDomains, 5000)
    return () => clearInterval(t)
  }, [domains, loadDomains])

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
          Point your domain's A record to our server, then connect it here — we handle the SSL certificate
          automatically.
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
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[d.status]}`}>
                      {d.status === 'registering' ? 'setting up…' : d.status}
                    </span>
                  </div>
                </div>
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
