import { useState, useEffect } from 'react'
import { Card } from '../../components/ui'
import { Button } from '../../components/ui'
import { Loader2 } from 'lucide-react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

const RESEARCH_MODELS = [
  { id: 'lite', label: 'Lite', model: 'Gemini 3.1 Flash Lite', description: 'Fastest, lowest cost — good for bulk research' },
  { id: 'light', label: 'Light', model: 'Gemini 3 Flash', description: 'Balanced speed and quality (default)' },
  { id: 'heavy', label: 'Pro', model: 'Gemini 3.1 Pro', description: 'Highest quality, slower — best for targeted research' },
]

export default function Settings() {
  const [researchMode, setResearchMode] = useState<string | null>(null)
  const [pendingMode, setPendingMode] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('matcha_access_token')
    fetch(`${BASE}/admin/platform-settings`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((data) => {
        const mode = data.jurisdiction_research_model_mode || 'light'
        setResearchMode(mode)
        setPendingMode(mode)
      })
      .catch(() => {
        setResearchMode('light')
        setPendingMode('light')
      })
      .finally(() => setLoading(false))
  }, [])

  async function handleSave() {
    if (!pendingMode || pendingMode === researchMode) return
    setSaving(true)
    const token = localStorage.getItem('matcha_access_token')
    try {
      const res = await fetch(`${BASE}/admin/platform-settings/jurisdiction-research-model-mode`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ mode: pendingMode }),
      })
      if (res.ok) {
        setResearchMode(pendingMode)
      }
    } finally {
      setSaving(false)
    }
  }

  const hasChanges = pendingMode !== researchMode

  return (
    <div>
      <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
        Settings
      </h1>
      <p className="mt-2 text-sm text-zinc-500">Platform-wide configuration.</p>

      <div className="mt-8 max-w-xl">
        <h2 className="text-sm font-medium text-zinc-300 mb-1">Compliance Research Model</h2>
        <p className="text-xs text-zinc-500 mb-3">
          Controls which Gemini model is used for jurisdiction &amp; specialization research.
        </p>

        {loading ? (
          <div className="flex items-center gap-2 py-4 text-sm text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading settings...
          </div>
        ) : (
          <div className="space-y-2">
            {RESEARCH_MODELS.map((m) => (
              <Card
                key={m.id}
                className={`flex items-center gap-4 p-4 cursor-pointer transition-colors ${
                  pendingMode === m.id
                    ? 'border-emerald-500 bg-emerald-950/20'
                    : 'hover:border-zinc-700'
                }`}
                onClick={() => setPendingMode(m.id)}
              >
                <div
                  className={`h-3 w-3 rounded-full border-2 shrink-0 ${
                    pendingMode === m.id
                      ? 'border-emerald-500 bg-emerald-500'
                      : 'border-zinc-600'
                  }`}
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-100">
                    {m.label}
                    <span className="ml-2 text-xs font-normal text-zinc-500">{m.model}</span>
                  </p>
                  <p className="text-xs text-zinc-500">{m.description}</p>
                </div>
              </Card>
            ))}
          </div>
        )}

        <div className="mt-6">
          <Button onClick={handleSave} disabled={!hasChanges || saving}>
            {saving ? 'Saving...' : hasChanges ? 'Save changes' : 'Saved'}
          </Button>
        </div>
      </div>
    </div>
  )
}
