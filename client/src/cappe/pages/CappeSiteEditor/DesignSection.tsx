import { Loader2, Check, Sparkles } from 'lucide-react'
import { CAPPE_THEMES, type CappeThemePreset } from '../../data/cappeThemes'
import type { CappeSite } from '../../types'

export function DesignSection({
  site, themeBusy, onApplyTheme,
}: {
  site: CappeSite
  themeBusy: string | null
  onApplyTheme: (preset: CappeThemePreset) => void
}) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-100">Design</h2>
        <span className="text-xs text-zinc-500">Applies instantly · re-publish to push live</span>
      </div>
      <p className="mb-4 text-xs text-zinc-500">Pick a look. Premium themes use designer fonts &amp; palettes.</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {CAPPE_THEMES.map((preset) => {
          const active = (site.theme_config?.preset as string) === preset.id
          const busy = themeBusy === preset.id
          return (
            <button
              key={preset.id}
              onClick={() => onApplyTheme(preset)}
              disabled={!!themeBusy}
              className={`group relative overflow-hidden rounded-xl border text-left transition disabled:opacity-60 ${
                active ? 'border-emerald-500 ring-1 ring-emerald-500' : 'border-zinc-700 hover:border-zinc-500'
              }`}
            >
              {/* swatch preview */}
              <div className="flex h-16 items-center gap-2 px-3" style={{ background: preset.swatch.bg }}>
                <div className="h-7 w-7 rounded-md" style={{ background: preset.swatch.brand }} />
                <div className="flex-1 space-y-1">
                  <div className="h-2 w-3/4 rounded" style={{ background: preset.swatch.text, opacity: 0.85 }} />
                  <div className="h-2 w-1/2 rounded" style={{ background: preset.swatch.surface }} />
                </div>
              </div>
              <div className="flex items-center justify-between gap-1 border-t border-zinc-800 bg-zinc-950 px-3 py-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1 text-xs font-semibold text-zinc-200">
                    {preset.name}
                    {preset.premium && (
                      <span className="inline-flex items-center gap-0.5 rounded bg-amber-500/15 px-1 py-0.5 text-[9px] font-bold uppercase text-amber-400">
                        <Sparkles className="h-2.5 w-2.5" /> Premium
                      </span>
                    )}
                  </div>
                  <div className="truncate text-[10px] text-zinc-500">{preset.font}</div>
                </div>
                {busy ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-emerald-400" />
                ) : active ? (
                  <Check className="h-4 w-4 shrink-0 text-emerald-400" />
                ) : null}
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}
