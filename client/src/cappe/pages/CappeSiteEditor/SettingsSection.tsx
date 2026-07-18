import { Loader2, Save } from 'lucide-react'
import ImageUpload from '../../components/ImageUpload'
import DomainManager from '../../components/DomainManager'
import { CAPPE_HOST } from '../../host'
import { CAPPE_TIMEZONES } from '../../data/timezones'
import { inputCls } from './styles'

export function SettingsSection({
  siteId, name, setName, subdomain, setSubdomain, timezone, setTimezone,
  logo, setLogo, saving, onSave,
}: {
  siteId: string
  name: string
  setName: (v: string) => void
  subdomain: string
  setSubdomain: (v: string) => void
  timezone: string
  setTimezone: (v: string) => void
  logo: string
  setLogo: (v: string) => void
  saving: boolean
  onSave: () => void
}) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
      <h2 className="mb-4 text-sm font-semibold text-zinc-100">Site settings</h2>
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Web address</label>
          <div className="flex items-center rounded-lg border border-zinc-700 bg-zinc-950 focus-within:border-emerald-500">
            <input
              value={subdomain}
              onChange={(e) => setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
              placeholder="your-name"
              className="min-w-0 flex-1 rounded-l-lg bg-transparent px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none"
            />
            <span className="shrink-0 px-3 text-sm text-zinc-500">.{CAPPE_HOST}</span>
          </div>
          <p className="mt-1 text-xs text-zinc-500">This is your site's public URL. Save to apply.</p>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Timezone</label>
          <select value={timezone} onChange={(e) => setTimezone(e.target.value)} className={inputCls}>
            {CAPPE_TIMEZONES.map((tz) => <option key={tz.value} value={tz.value}>{tz.label}</option>)}
          </select>
          <p className="mt-1 text-xs text-zinc-500">Booking times show in this zone. Set it so customers see the right hours.</p>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Logo</label>
          <ImageUpload siteId={siteId || ''} value={logo} onChange={setLogo} placeholder="Logo image URL" />
          <p className="mt-1 text-xs text-zinc-500">Shown in your published site's header. Save to apply.</p>
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium text-zinc-300">Custom domain</label>
          <DomainManager siteId={siteId || ''} />
        </div>
        <button
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-60"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save changes
        </button>
      </div>
    </section>
  )
}
