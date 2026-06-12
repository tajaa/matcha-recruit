import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, LayoutTemplate, Check } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import type { CappeSite, CappeTemplateSummary } from '../../types/cappe'

export default function CappeTemplates() {
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<CappeTemplateSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [usingId, setUsingId] = useState<string | null>(null)

  useEffect(() => {
    // Catalog is public, but the authed client works fine here too.
    cappeApi
      .get<CappeTemplateSummary[]>('/templates')
      .then(setTemplates)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load templates'))
  }, [])

  async function useTemplate(t: CappeTemplateSummary) {
    setUsingId(t.id)
    setError(null)
    try {
      const site = await cappeApi.post<CappeSite>('/sites/from-template', {
        template_id: t.id,
        name: t.name,
      })
      navigate(`/cappe/sites/${site.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create site')
      setUsingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Templates</h1>
        <p className="mt-1 text-sm text-zinc-500">Pick a starting point — we'll clone it into a new site.</p>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {templates === null ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <div key={t.id} className="flex flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
              <div className="flex h-36 items-center justify-center bg-gradient-to-br from-zinc-50 to-zinc-100">
                {t.preview_image_url ? (
                  <img src={t.preview_image_url} alt={t.name} className="h-full w-full object-cover" />
                ) : (
                  <LayoutTemplate className="h-8 w-8 text-zinc-300" />
                )}
              </div>
              <div className="flex flex-1 flex-col p-5">
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="font-medium text-zinc-900">{t.name}</h3>
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-zinc-500">
                    {t.category}
                  </span>
                </div>
                <p className="mb-4 flex-1 text-sm text-zinc-500">{t.description}</p>
                <button
                  onClick={() => useTemplate(t)}
                  disabled={usingId !== null}
                  className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
                >
                  {usingId === t.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Use this template
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
