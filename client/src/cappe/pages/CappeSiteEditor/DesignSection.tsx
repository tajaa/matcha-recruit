import { Link } from 'react-router-dom'
import { Loader2, Check, Sparkles, Lock, RotateCcw } from 'lucide-react'
import { CAPPE_THEMES, type CappeThemePreset } from '../../data/cappeThemes'
import { useCappeMe } from '../../hooks/useCappeMe'
import { isPremiumPlan } from '../../utils/plan'
import { confirmLeave } from '../../utils/unsavedGuard'
import { BILLING_PATH } from '../CappeBilling/paths'
import type { CappeSite } from '../../types'
import { TEMPLATE_RESET_KEY } from './useCappeSiteEditor'

export function DesignSection({
  site, themeBusy, onApplyTheme, onResetTemplate,
}: {
  site: CappeSite
  themeBusy: string | null
  onApplyTheme: (preset: CappeThemePreset) => void
  onResetTemplate: () => void
}) {
  const { account } = useCappeMe()
  const premium = isPremiumPlan(account?.plan)
  const templateBusy = themeBusy === TEMPLATE_RESET_KEY

  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-100">Design</h2>
        <span className="text-xs text-zinc-500">Applies instantly · re-publish to push live</span>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Pick a look. Premium themes use designer fonts &amp; palettes
        {premium ? '.' : (
          <>
            {' '}— included on paid plans.{' '}
            {/* The one deliberate way out of this page from here. Locked cards
                themselves are inert: a card in a grid of apply-buttons that
                navigated away took unsaved settings edits with it. */}
            <Link
              to={BILLING_PATH}
              onClick={(e) => { if (!confirmLeave()) e.preventDefault() }}
              className="font-semibold text-amber-300 underline underline-offset-2 hover:text-amber-200"
            >
              See plans
            </Link>
          </>
        )}
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {site.template_slug && (
          <button
            type="button"
            onClick={onResetTemplate}
            disabled={!!themeBusy}
            aria-label="Restore the template's original design"
            // Never shown as "active": `theme_config.template` survives every
            // colour, font and Merlin edit, so it cannot tell an untouched
            // theme from an edited one — and a card that believed it could
            // was disabled exactly when the reset was needed.
            className="group relative overflow-hidden rounded-xl border border-dashed border-zinc-600 text-left transition hover:border-zinc-400 disabled:opacity-60"
          >
            <div className="flex h-16 items-center justify-center gap-2 bg-zinc-950 px-3 text-zinc-400">
              <RotateCcw className="h-5 w-5" />
            </div>
            <div className="flex items-center justify-between gap-1 border-t border-zinc-800 bg-zinc-950 px-3 py-2">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-zinc-200">Template original</div>
                <div className="truncate text-[10px] text-zinc-500">Back to how it started</div>
              </div>
              {templateBusy && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-emerald-400" />}
            </div>
          </button>
        )}
        {CAPPE_THEMES.map((preset) => {
          const active = (site.theme_config?.preset as string) === preset.id
          const busy = themeBusy === preset.id
          const locked = preset.premium && !premium
          const swatch = (
            <div className="flex h-16 items-center gap-2 px-3" style={{ background: preset.swatch.bg }}>
              <div className="h-7 w-7 rounded-md" style={{ background: preset.swatch.brand }} />
              <div className="flex-1 space-y-1">
                <div className="h-2 w-3/4 rounded" style={{ background: preset.swatch.text, opacity: 0.85 }} />
                <div className="h-2 w-1/2 rounded" style={{ background: preset.swatch.surface }} />
              </div>
            </div>
          )
          const caption = (
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
              ) : locked ? (
                <Lock className="h-3.5 w-3.5 shrink-0 text-amber-400/80" />
              ) : null}
            </div>
          )
          // A locked preset used to apply and then quietly lose its premium
          // keys on save — a theme that looked different from what it kept.
          // Now the card is inert and says why; "See plans" above is the way on.
          if (locked) {
            return (
              <div
                key={preset.id}
                role="group"
                aria-disabled="true"
                aria-label={`${preset.name} theme — included on paid plans`}
                title="Included on paid plans"
                className="relative cursor-not-allowed overflow-hidden rounded-xl border border-zinc-800 text-left opacity-70"
              >
                {swatch}
                {caption}
              </div>
            )
          }
          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => onApplyTheme(preset)}
              disabled={!!themeBusy}
              className={`group relative overflow-hidden rounded-xl border text-left transition disabled:opacity-60 ${
                active ? 'border-emerald-500 ring-1 ring-emerald-500' : 'border-zinc-700 hover:border-zinc-500'
              }`}
            >
              {swatch}
              {caption}
            </button>
          )
        })}
      </div>
    </section>
  )
}
