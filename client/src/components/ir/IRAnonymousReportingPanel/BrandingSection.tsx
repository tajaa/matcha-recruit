import { Button } from '../../ui'
import type { Branding } from './types'
import { ColorField } from './ColorField'
import { PosterPreview } from './PosterPreview'

interface BrandingSectionProps {
  branding: Branding
  brandingLoading: boolean
  brandingSaving: boolean
  brandingDirty: boolean
  brandingSaved: boolean
  updateBrand: (k: keyof Branding, v: string) => void
  resetBranding: () => void
  saveBranding: () => void
}

export function BrandingSection({
  branding,
  brandingLoading,
  brandingSaving,
  brandingDirty,
  brandingSaved,
  updateBrand,
  resetBranding,
  saveBranding,
}: BrandingSectionProps) {
  return (
    <div className="space-y-3">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">QR poster branding</p>
      <p className="text-[11px] text-zinc-500">
        Recolor the printable QR poster to match your brand. Matcha branding stays on every poster.
      </p>
      {brandingLoading ? (
        <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono animate-pulse">Loading…</p>
      ) : (
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1 space-y-3">
            <ColorField label="Primary (background)" value={branding.primary} onChange={(v) => updateBrand('primary', v)} />
            <ColorField label="Secondary (accents)" value={branding.secondary} onChange={(v) => updateBrand('secondary', v)} />
            <div className="flex items-center gap-2 pt-1">
              <Button size="sm" disabled={brandingSaving || !brandingDirty} onClick={saveBranding}>
                {brandingSaved ? 'Saved' : 'Save branding'}
              </Button>
              <Button size="sm" variant="ghost" disabled={brandingSaving} onClick={resetBranding}>
                Reset to default
              </Button>
            </div>
            <p className="text-[11px] text-zinc-600">
              "HEY-MATCHA.COM" and "Powered by Matcha" always appear; title text auto-adjusts for contrast.
            </p>
          </div>
          <div className="flex flex-col items-center gap-1">
            <PosterPreview primary={branding.primary} secondary={branding.secondary} />
            <span className="text-[10px] text-zinc-600 uppercase tracking-widest">Preview</span>
          </div>
        </div>
      )}
    </div>
  )
}
