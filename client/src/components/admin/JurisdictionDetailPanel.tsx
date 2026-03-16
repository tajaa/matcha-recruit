import { useEffect, useState, useCallback } from 'react'
import { api } from '../../api/client'
import { Button } from '../ui'
import { categoryLabel } from '../../types/compliance'
import type { RequirementCategory } from '../../types/compliance'

type JurisdictionReq = {
  id: string
  category: string
  jurisdiction_level: string
  title: string
  current_value: string | null
  effective_date: string | null
  is_bookmarked: boolean
}

type LinkedLocation = {
  id: string
  name: string | null
  city: string
  company_name: string
}

type JurisdictionDetail = {
  id: string
  city: string
  state: string
  requirements: JurisdictionReq[]
  locations: LinkedLocation[]
}

type Props = {
  id: string
  city: string
  state: string
  categoriesMissing?: string[]
  onCheckComplete?: () => void
}

function getCategoryLabel(cat: string) {
  return categoryLabel[cat as RequirementCategory] ?? cat
}

export default function JurisdictionDetailPanel({ id, city, state, categoriesMissing, onCheckComplete }: Props) {
  const [detail, setDetail] = useState<JurisdictionDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanMessages, setScanMessages] = useState<string[]>([])

  const fetchDetail = useCallback(async () => {
    setLoading(true); setDetail(null); setScanMessages([])
    try { setDetail(await api.get<JurisdictionDetail>(`/admin/jurisdictions/${id}`)) }
    catch { setDetail(null) }
    finally { setLoading(false) }
  }, [id])

  useEffect(() => { fetchDetail() }, [fetchDetail])

  function startCheck() {
    setScanning(true); setScanMessages([])
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/admin/jurisdictions/${id}/check`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    }).then(async (res) => {
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) return
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (line.startsWith(': ')) continue
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') {
            setScanning(false)
            fetchDetail()
            onCheckComplete?.()
            return
          }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setScanMessages((p) => [...p, `Error: ${ev.message}`]); setScanning(false); return }
            if (ev.message) setScanMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setScanning(false)
    }).catch(() => setScanning(false))
  }

  const groupedReqs = (detail?.requirements ?? []).reduce<Record<string, JurisdictionReq[]>>((acc, r) => {
    if (!acc[r.category]) acc[r.category] = []
    acc[r.category].push(r)
    return acc
  }, {})

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-medium text-zinc-100">{city}, {state}</h2>
          {detail && (
            <p className="text-[11px] text-zinc-500 mt-0.5">
              {detail.requirements.length} requirements · {detail.locations.length} linked locations
            </p>
          )}
        </div>
        <Button variant="secondary" size="sm" disabled={scanning || loading} onClick={startCheck}>
          {scanning ? 'Scanning...' : 'Run Check'}
        </Button>
      </div>

      {/* Missing categories */}
      {categoriesMissing && categoriesMissing.length > 0 && (
        <div className="mb-3 border border-zinc-800 rounded-lg px-3 py-2.5">
          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1.5">Missing categories</p>
          <div className="flex flex-wrap gap-1.5">
            {categoriesMissing.map((cat) => (
              <span key={cat} className="text-[11px] text-zinc-500 bg-zinc-800/60 px-2 py-0.5 rounded">
                {getCategoryLabel(cat)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* SSE scan log */}
      {scanning && scanMessages.length > 0 && (
        <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
          {scanMessages.map((msg, i) => (
            <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
          ))}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : !detail ? (
        <p className="text-sm text-zinc-600">Failed to load detail.</p>
      ) : detail.requirements.length === 0 ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-600">No requirements yet — run a check to populate.</p>
        </div>
      ) : (
        <div className="border border-zinc-800 rounded-lg max-h-[60vh] overflow-y-auto">
          {Object.entries(groupedReqs).map(([cat, reqs], catIdx) => (
            <div key={cat}>
              {catIdx > 0 && <div className="border-t border-zinc-800/60" />}
              <div className="px-4 pt-3 pb-1">
                <p className="text-xs uppercase tracking-wide text-zinc-400">{getCategoryLabel(cat)}</p>
              </div>
              {reqs.map((req) => (
                <div key={req.id} className="flex items-start gap-3 px-4 py-2 border-t border-zinc-800/30">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200">{req.title}</p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-[11px] text-zinc-500">{req.jurisdiction_level}</span>
                      {req.current_value && (
                        <>
                          <span className="text-[11px] text-zinc-600">·</span>
                          <span className="text-[11px] text-zinc-400">{req.current_value}</span>
                        </>
                      )}
                      {req.effective_date && (
                        <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>
                      )}
                    </div>
                  </div>
                  {req.is_bookmarked && <span className="text-[11px] text-zinc-500 shrink-0">★</span>}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Linked locations */}
      {detail && detail.locations.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1.5">Linked Business Locations</p>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {detail.locations.map((loc) => (
              <div key={loc.id} className="flex items-center justify-between px-3 py-2">
                <p className="text-sm text-zinc-300">{loc.company_name}</p>
                <p className="text-[11px] text-zinc-500">{loc.name || loc.city}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
