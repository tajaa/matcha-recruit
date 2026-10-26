import { AgentModelsSetting } from '../../../components/admin/AgentModelsSetting'
import { AdminPageHeader } from '../../../components/admin/AdminPageHeader'
import { AdminButton } from '../../../components/admin/AdminUI'
import { adminSettingsApi } from '../../../api/admin/platformSettings'
import { useAsync } from '../../../hooks/useAsync'

export default function GummfitModels() {
  const settings = useAsync(() => adminSettingsApi.getPlatformSettings(), [])
  const data = settings.data
  const registry = data?.agent_model_registry?.filter((app) => app.key === 'gummfit') ?? []

  return (
    <div>
      <AdminPageHeader title="AI models" description="Choose Gummfit’s default AI model and overrides for each product." />
      {settings.loading ? <p className="text-sm text-zinc-500">Loading settings…</p>
        : settings.error || !data?.agent_models || registry.length === 0 ? (
          <div role="alert" className="space-y-3">
            <p className="text-sm text-red-400">{settings.error || 'Gummfit model settings are unavailable. Reload and try again.'}</p>
            <AdminButton onClick={() => void settings.reload()}>Retry</AdminButton>
          </div>
        ) : (
          <AgentModelsSetting
            models={data.agent_models}
            registry={registry}
            choices={data.agent_model_choices ?? []}
            version={data.agent_models_version ?? null}
            anthropicConfigured={!!data.anthropic_configured}
            onSaved={(models, version) => settings.setData({ ...data, agent_models: models, agent_models_version: version })}
          />
        )}
    </div>
  )
}
