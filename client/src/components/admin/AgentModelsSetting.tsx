import { useId, useState } from 'react'
import { Button, Card, Select } from '../ui'
import {
  adminSettingsApi,
  type AgentModelApp,
  type AgentModelChoice,
  type AgentModels,
} from '../../api/admin/platformSettings'

const INHERIT = 'inherit'
const BUILTIN = 'default'

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** The label for a stored choice; `short` drops "Claude " so "Same as Matcha:
 *  Haiku 5.5" fits the select. The Claude labels come from the server. */
function choiceLabel(choices: AgentModelChoice[], value: string, short = false) {
  if (value === BUILTIN) return 'Built-in'
  const label = choices.find((c) => c.id === value)?.label ?? value
  return short ? label.replace(/^Claude /, '') : label
}

/** Claude rows only while the server has a key; a value already stored stays
 *  listed so the menu never hides what is saved. */
function claudeOptions(choices: AgentModelChoice[], anthropicConfigured: boolean, current: string) {
  return choices
    .filter((c) => anthropicConfigured || c.id === current)
    .map((c) => ({ value: c.id, label: c.label }))
}

interface AgentModelsSettingProps {
  /** The stored map, as GET /admin/platform-settings returns it. */
  models: AgentModels
  /** The apps and products to list — the server's registry, not hard-coded here. */
  registry: AgentModelApp[]
  /** The Claude models on offer, with labels — also the server's. */
  choices: AgentModelChoice[]
  /** The loaded map's version; a save from an outdated page is refused (409). */
  version: string | null
  /** False while ANTHROPIC_API_KEY is unset: Claude cannot be newly picked. */
  anthropicConfigured: boolean
  onSaved(models: AgentModels, version: string): void
}

/** Admin → Settings → AI models: one model per app, which each product can
 *  follow ("Same as …") or override. The schedule assistant's own dropdown
 *  still lets a manager pick per chat. */
export function AgentModelsSetting({
  models, registry, choices, version, anthropicConfigured, onSaved,
}: AgentModelsSettingProps) {
  const [pending, setPending] = useState<AgentModels | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const draft = pending ?? models
  const dirty = pending !== null && JSON.stringify(pending) !== JSON.stringify(models)

  const setApp = (app: string, value: string) =>
    setPending({ ...draft, apps: { ...draft.apps, [app]: value } })
  const setSurface = (surface: string, value: string) =>
    setPending({ ...draft, surfaces: { ...draft.surfaces, [surface]: value } })

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const saved = await adminSettingsApi.setAgentModels({ ...draft, version })
      onSaved(saved.agent_models, saved.version)
      setPending(null)
    } catch (e) {
      setError(errText(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      {registry.map((app) => {
        const appValue = draft.apps[app.key] ?? BUILTIN
        return (
          <Card key={app.key} className="p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-zinc-100">{app.label}</p>
                <p className="text-xs text-zinc-500">{app.description}</p>
              </div>
              <Select
                className="w-full shrink-0 sm:w-60"
                label={`${app.label} default`}
                value={appValue}
                onChange={(e) => setApp(app.key, e.target.value)}
                options={[
                  { value: BUILTIN, label: 'Built-in (each product\'s own)' },
                  ...claudeOptions(choices, anthropicConfigured, appValue),
                ]}
              />
            </div>
            {app.surfaces.length > 0 && (
              <ul className="mt-4 divide-y divide-zinc-800 border-t border-zinc-800">
                {app.surfaces.map((surface) => (
                  <SurfaceRow
                    key={surface.key}
                    surface={surface}
                    appLabel={app.label}
                    appValue={appValue}
                    choices={choices}
                    value={draft.surfaces[surface.key] ?? INHERIT}
                    anthropicConfigured={anthropicConfigured}
                    onChange={(value) => setSurface(surface.key, value)}
                  />
                ))}
              </ul>
            )}
          </Card>
        )
      })}
      {!anthropicConfigured && (
        <p className="text-xs text-zinc-500">Claude needs ANTHROPIC_API_KEY on the server.</p>
      )}
      <p className="text-xs text-zinc-500">
        Changes reach every server within about 30 seconds; a run already going keeps its model.
      </p>
      <div>
        <Button onClick={save} disabled={!dirty || saving}>
          {saving ? 'Saving...' : dirty ? 'Save changes' : 'Saved'}
        </Button>
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      </div>
    </div>
  )
}

interface SurfaceRowProps {
  surface: AgentModelApp['surfaces'][number]
  appLabel: string
  appValue: string
  choices: AgentModelChoice[]
  value: string
  anthropicConfigured: boolean
  onChange(value: string): void
}

/** One product: its name labels the select (no repeated caption), and the
 *  built-in model sits under the description rather than in the option. */
function SurfaceRow({ surface, appLabel, appValue, choices, value, anthropicConfigured, onChange }: SurfaceRowProps) {
  const selectId = useId()
  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="min-w-0 flex-1">
        <label htmlFor={selectId} className="text-sm text-zinc-200">{surface.label}</label>
        <p className="text-xs text-zinc-500">{surface.description}</p>
        <p className="mt-0.5 text-[11px] text-zinc-600">Built-in: {surface.builtin}</p>
      </div>
      <Select
        id={selectId}
        className="w-full shrink-0 sm:w-60"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        options={[
          { value: INHERIT, label: `Same as ${appLabel}: ${choiceLabel(choices, appValue, true)}` },
          { value: BUILTIN, label: 'Built-in' },
          ...claudeOptions(choices, anthropicConfigured, value),
        ]}
      />
    </li>
  )
}
