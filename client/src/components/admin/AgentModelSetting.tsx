import { useState } from 'react'
import { Button, Card } from '../ui'
import { adminSettingsApi } from '../../api/admin/platformSettings'

export const DEFAULT_AGENT_MODEL = 'default'

const AGENT_MODELS = [
  {
    id: DEFAULT_AGENT_MODEL,
    label: 'Default',
    model: 'Luna / Gemini',
    description: 'Each feature runs on the model it was built on: Luna for Huume and the Espresso agents, Gemini for Ops channel @huume.',
    claude: false,
  },
  {
    id: 'claude-haiku-5-5',
    label: 'Claude Haiku 5.5',
    model: 'Anthropic',
    description: 'Fastest and cheapest Claude, for high-volume chat and tool work.',
    claude: true,
  },
  {
    id: 'claude-sonnet-5-5',
    label: 'Claude Sonnet 5.5',
    model: 'Anthropic',
    description: 'Stronger reasoning for multi-step agent work, at a higher cost per call.',
    claude: true,
  },
]

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

interface AgentModelSettingProps {
  /** The stored choice, as GET /admin/platform-settings returns it. */
  current: string
  /** False while ANTHROPIC_API_KEY is unset: Claude is shown but cannot be picked. */
  anthropicConfigured: boolean
  onSaved(model: string): void
}

/** The platform "Agent model" switch: one choice for every Luna/Gemini agent
 *  and one-shot workload. The schedule assistant's own dropdown still lets a
 *  manager override it per chat. */
export function AgentModelSetting({ current, anthropicConfigured, onSaved }: AgentModelSettingProps) {
  const [pending, setPending] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selected = pending ?? current
  const dirty = selected !== current

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const saved = await adminSettingsApi.setAgentModel(selected)
      onSaved(saved.agent_model)
      setPending(null)
    } catch (e) {
      setError(errText(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="space-y-2" role="radiogroup" aria-label="Agent model">
        {AGENT_MODELS.map((m) => {
          const disabled = m.claude && !anthropicConfigured
          const active = selected === m.id
          return (
            <Card
              key={m.id}
              role="radio"
              aria-checked={active}
              aria-disabled={disabled}
              className={`flex items-center gap-4 p-4 transition-colors ${
                disabled ? 'cursor-not-allowed opacity-50'
                  : active ? 'cursor-pointer border-emerald-500 bg-emerald-950/20' : 'cursor-pointer hover:border-zinc-700'
              }`}
              onClick={() => { if (!disabled) setPending(m.id) }}
            >
              <div className={`h-3 w-3 rounded-full border-2 shrink-0 ${
                active ? 'border-emerald-500 bg-emerald-500' : 'border-zinc-600'
              }`} />
              <div className="min-w-0">
                <p className="text-sm font-medium text-zinc-100">
                  {m.label} <span className="ml-2 text-xs font-normal text-zinc-500">{m.model}</span>
                </p>
                <p className="text-xs text-zinc-500">{m.description}</p>
              </div>
            </Card>
          )
        })}
      </div>
      {!anthropicConfigured && (
        <p className="mt-2 text-xs text-zinc-500">Claude needs ANTHROPIC_API_KEY on the server.</p>
      )}
      <div className="mt-6">
        <Button onClick={save} disabled={!dirty || saving}>
          {saving ? 'Saving...' : dirty ? 'Save changes' : 'Saved'}
        </Button>
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      </div>
    </div>
  )
}
