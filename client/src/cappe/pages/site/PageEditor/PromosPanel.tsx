import { useState } from 'react'
import { Megaphone } from 'lucide-react'
import { ImageInput } from './FieldInputs'
import { DCheck, DColor, DNum, DSelect, PremiumLock } from './DesignPrimitives'
import { dHead, dLabel, inputCls } from './styles'
import { isOn, obj, str } from './valueHelpers'

export function PInput({ label, value, onChange, ph, area }: {
  label: string; value: unknown; onChange: (v: string) => void; ph?: string; area?: boolean
}) {
  return (
    <label className="block"><span className={dLabel}>{label}</span>
      {area
        ? <textarea value={str(value)} onChange={(e) => onChange(e.target.value)} rows={2} placeholder={ph} className={`${inputCls} py-1.5`} />
        : <input value={str(value)} onChange={(e) => onChange(e.target.value)} placeholder={ph} className={`${inputCls} py-1.5`} />}
    </label>
  )
}

/** Site-wide promotions editor: an announcement bar + a pop-up modal stored on
 *  the site's meta_config.promos. Pro/Business only. Previews live; saved on the
 *  page editor's Save. */
export function PromosPanel({ meta, premium, onChange, dirty }: {
  meta: Record<string, unknown>
  premium: boolean
  onChange: (m: Record<string, unknown>) => void
  dirty: boolean
}) {
  const [open, setOpen] = useState(false)
  const promos = obj(meta.promos)
  const bar = obj(promos.bar)
  const popup = obj(promos.popup)
  const patch = (group: 'bar' | 'popup', key: string, value: unknown) =>
    onChange({ ...meta, promos: { ...promos, [group]: { ...obj(promos[group]), [key]: value } } })
  const popMode = str(popup.mode) || 'newsletter'
  const popTrigger = str(popup.trigger) || 'load'

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${open ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}>
        <Megaphone className="h-4 w-4" /> Promos{dirty && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-30 mt-1 max-h-[80vh] w-80 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-3 shadow-2xl shadow-black/50">
            {!premium ? (
              <PremiumLock>Upgrade to Pro to add sale banners &amp; pop-ups that grow your list.</PremiumLock>
            ) : (
              <>
                {/* Announcement bar */}
                <section className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <p className={dHead}>Announcement bar</p>
                    <DCheck label="On" checked={isOn(bar.enabled)} onChange={(v) => patch('bar', 'enabled', v)} />
                  </div>
                  {isOn(bar.enabled) && (
                    <>
                      <PInput label="Message" value={bar.text} onChange={(v) => patch('bar', 'text', v)} ph="Summer sale — 20% off everything" />
                      <div className="grid grid-cols-2 gap-2">
                        <PInput label="Button label" value={bar.ctaLabel} onChange={(v) => patch('bar', 'ctaLabel', v)} ph="Shop now" />
                        <PInput label="Button link" value={bar.ctaHref} onChange={(v) => patch('bar', 'ctaHref', v)} ph="/p/shop" />
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <DSelect label="Position" value={str(bar.position) || 'top'} onChange={(v) => patch('bar', 'position', v)} options={[['top', 'Top'], ['bottom', 'Bottom (sticky)']]} />
                        <div className="flex items-end pb-1"><DCheck label="Dismissible" checked={isOn(bar.dismissible)} onChange={(v) => patch('bar', 'dismissible', v)} /></div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <DColor label="Background" value={str(bar.bg)} onChange={(v) => patch('bar', 'bg', v)} />
                        <DColor label="Text" value={str(bar.color)} onChange={(v) => patch('bar', 'color', v)} />
                      </div>
                    </>
                  )}
                </section>

                {/* Pop-up modal */}
                <section className="mt-3 space-y-2.5 border-t border-zinc-800 pt-3">
                  <div className="flex items-center justify-between">
                    <p className={dHead}>Pop-up</p>
                    <DCheck label="On" checked={isOn(popup.enabled)} onChange={(v) => patch('popup', 'enabled', v)} />
                  </div>
                  {isOn(popup.enabled) && (
                    <>
                      <div className="grid grid-cols-2 gap-2">
                        <DSelect label="Show on" value={popTrigger} onChange={(v) => patch('popup', 'trigger', v)} options={[['load', 'Page load'], ['delay', 'After delay'], ['exit', 'Exit intent']]} />
                        {popTrigger === 'delay'
                          ? <DNum label="Delay (sec)" value={Number(popup.delaySec) || 5} min={0} max={120} onChange={(v) => patch('popup', 'delaySec', v)} />
                          : <DSelect label="Frequency" value={str(popup.frequency) || 'session'} onChange={(v) => patch('popup', 'frequency', v)} options={[['session', 'Once / visit'], ['once', 'Once ever'], ['always', 'Every load']]} />}
                      </div>
                      {popTrigger === 'delay' && (
                        <DSelect label="Frequency" value={str(popup.frequency) || 'session'} onChange={(v) => patch('popup', 'frequency', v)} options={[['session', 'Once / visit'], ['once', 'Once ever'], ['always', 'Every load']]} />
                      )}
                      <DSelect label="Goal" value={popMode} onChange={(v) => patch('popup', 'mode', v)} options={[['newsletter', 'Collect emails'], ['code', 'Show discount code'], ['cta', 'Call to action']]} />
                      <PInput label="Heading" value={popup.heading} onChange={(v) => patch('popup', 'heading', v)} ph="Get 10% off your first order" />
                      <PInput label="Body" value={popup.body} onChange={(v) => patch('popup', 'body', v)} ph="Join our list for early drops & deals." area />
                      <div><span className={dLabel}>Image (optional)</span><ImageInput value={popup.image} onChange={(v) => patch('popup', 'image', v)} /></div>
                      {popMode === 'newsletter' && <PInput label="Button label" value={popup.ctaLabel} onChange={(v) => patch('popup', 'ctaLabel', v)} ph="Subscribe" />}
                      {popMode === 'code' && (
                        <div className="grid grid-cols-2 gap-2">
                          <PInput label="Discount code" value={popup.code} onChange={(v) => patch('popup', 'code', v)} ph="WELCOME10" />
                          <PInput label="Button label" value={popup.ctaLabel} onChange={(v) => patch('popup', 'ctaLabel', v)} ph="Shop now" />
                        </div>
                      )}
                      {popMode === 'cta' && (
                        <div className="grid grid-cols-2 gap-2">
                          <PInput label="Button label" value={popup.ctaLabel} onChange={(v) => patch('popup', 'ctaLabel', v)} ph="Learn more" />
                          <PInput label="Button link" value={popup.ctaHref} onChange={(v) => patch('popup', 'ctaHref', v)} ph="/p/about" />
                        </div>
                      )}
                      {popMode === 'code' && (
                        <PInput label="Button link" value={popup.ctaHref} onChange={(v) => patch('popup', 'ctaHref', v)} ph="/p/shop" />
                      )}
                      <DColor label="Card background" value={str(popup.bg)} onChange={(v) => patch('popup', 'bg', v)} />
                    </>
                  )}
                </section>
                <p className="mt-3 text-[11px] text-zinc-500">Previews live (switch to Form preview to see the pop-up). <span className="text-zinc-300">Save</span> to publish.</p>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
