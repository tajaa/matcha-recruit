import { useState } from 'react'
import { api } from '../../../api/client'

export type ProposedCategory = {
  key: string
  label?: string
  description?: string
  authority_sources?: string[]
  is_existing?: boolean
}

export type DiscoverResponse = {
  industry: string
  slug: string
  label: string
  industry_tag: string
  categories: ProposedCategory[]
  research_context: string
}

// Specialty derive/confirm modal (from IndustryRequirements, verbatim shape).
export default function SpecialtyReviewModal({
  proposal, industry, onCancel, onConfirmed,
}: {
  proposal: DiscoverResponse
  industry: string
  onCancel: () => void
  onConfirmed: (slug: string) => void
}) {
  const novel = proposal.categories.filter((c) => !c.is_existing)
  const existing = proposal.categories.filter((c) => c.is_existing)
  const [selected, setSelected] = useState<Set<string>>(new Set(novel.map((c) => c.key)))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  const confirm = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.post(`/admin/industries/${encodeURIComponent(industry)}/specialties/confirm`, {
        slug: proposal.slug,
        label: proposal.label,
        research_context: proposal.research_context,
        categories: novel.filter((c) => selected.has(c.key)),
      })
      onConfirmed(proposal.slug)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to confirm scope')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-white/[0.08] bg-zinc-900 p-6">
        <h3 className="text-lg font-semibold text-zinc-100">
          Confirm scope for {proposal.label}
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          Confirming records these as applicable compliance categories with no
          regulations behind them yet — they appear in the matrix as “to codify”.
        </p>

        <div className="mt-4 space-y-2">
          {novel.map((c) => (
            <label
              key={c.key}
              className="flex cursor-pointer gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 hover:border-white/20"
            >
              <input
                type="checkbox"
                checked={selected.has(c.key)}
                onChange={() => toggle(c.key)}
                className="mt-1"
              />
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-200">{c.label || c.key}</div>
                <div className="font-mono text-xs text-zinc-500">{c.key}</div>
                {c.description && <div className="mt-1 text-xs text-zinc-400">{c.description}</div>}
                {c.authority_sources?.length ? (
                  <div className="mt-1 text-xs text-zinc-500">
                    Authorities: {c.authority_sources.join(', ')}
                  </div>
                ) : null}
              </div>
            </label>
          ))}
        </div>

        {existing.length > 0 && (
          <details className="mt-3 text-xs text-zinc-500">
            <summary className="cursor-pointer">{existing.length} already in the baseline</summary>
            <div className="mt-1 space-y-0.5">
              {existing.map((c) => (
                <div key={c.key} className="font-mono">{c.key}</div>
              ))}
            </div>
          </details>
        )}

        {error && <div className="mt-3 text-sm text-red-400">{error}</div>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-zinc-300 hover:bg-white/[0.04]"
          >
            Cancel
          </button>
          <button
            onClick={confirm}
            disabled={saving || selected.size === 0}
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {saving ? 'Saving…' : `Confirm scope (${selected.size})`}
          </button>
        </div>
      </div>
    </div>
  )
}
