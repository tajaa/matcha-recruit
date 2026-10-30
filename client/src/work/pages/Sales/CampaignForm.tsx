import { useState } from 'react'
import type { CampaignInput, HouseOffer, SalesCampaign, SalesPlaybook } from '../../api/matchaWork/sales'
import { FOOTER_PLACEHOLDER } from './salesLogic'

const input = 'w-full rounded-md border border-w-line bg-w-surface2/50 px-2.5 py-1.5 text-xs text-w-text outline-none focus:border-w-accent/60'
const label = 'block space-y-1 text-[11px] font-semibold text-w-dim'

/**
 * A new campaign, or the open one's settings. The consulting playbook adds a
 * booking link every message asks for; Matcha staff can start from Matcha's
 * own consulting offer (`house`), whose fields fill what is left empty.
 */
export default function CampaignForm({ campaign, house, busy, onSave, onCancel }: {
  campaign?: SalesCampaign
  house: HouseOffer | null
  busy: boolean
  /** A new campaign gets every field; settings get only what changed. */
  onSave: (input: Partial<CampaignInput>) => Promise<unknown>
  onCancel?: () => void
}) {
  const [title, setTitle] = useState(campaign?.title ?? '')
  const [playbook, setPlaybook] = useState<SalesPlaybook>(campaign?.playbook ?? '')
  const [useHouse, setUseHouse] = useState(false)
  const [target, setTarget] = useState(campaign?.target ?? '')
  const [offer, setOffer] = useState(campaign?.offer ?? '')
  const [ctaUrl, setCtaUrl] = useState(campaign?.cta_url ?? '')
  const [footer, setFooter] = useState(campaign?.footer ?? '')
  const consulting = playbook === 'consulting' || useHouse

  function startFromHouse(on: boolean) {
    setUseHouse(on)
    if (on && house) {
      setPlaybook('consulting')
      setTitle((t) => t || house.title)
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const values = {
      title: title.trim(),
      target: target.trim(),
      offer: offer.trim(),
      footer: footer.trim(),
      playbook: (consulting ? 'consulting' : '') as SalesPlaybook,
      cta_url: consulting ? ctaUrl.trim() : '',
    }
    if (!campaign) {
      await onSave({ ...values, house: useHouse })
      return
    }
    // Settings send only what was changed here: a stored value with stray
    // whitespace (saved from the Mac or by Espresso) isn't a change, so it
    // can't trip "the footer is frozen while messages are pending".
    const typed = { title, target, offer, footer, playbook: values.playbook, cta_url: consulting ? ctaUrl : '' }
    const changes = Object.fromEntries(
      (Object.keys(values) as (keyof typeof values)[])
        .filter((key) => typed[key] !== (campaign[key] ?? ''))
        .map((key) => [key, values[key]]),
    )
    await onSave(changes)
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3">
      {!campaign && house && (
        <label className="flex items-start gap-2 rounded-md border border-w-accent/30 bg-w-accent/5 p-2.5 text-xs text-w-text">
          <input type="checkbox" checked={useHouse} onChange={(e) => startFromHouse(e.target.checked)} className="mt-0.5" />
          <span>
            <span className="font-semibold">Start from Matcha's consulting offer</span>
            <span className="block text-[11px] text-w-dim">
              Our four services and the booking link ({house.cta_url}). Anything you write below takes its place.
            </span>
          </span>
        </label>
      )}
      <label className={label}>
        Name
        <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={100} className={input} />
      </label>
      <label className={label}>
        Kind
        <select value={consulting ? 'consulting' : ''} disabled={useHouse}
          onChange={(e) => setPlaybook(e.target.value as SalesPlaybook)} className={input}>
          <option value="">General outreach</option>
          <option value="consulting">Consulting outreach</option>
        </select>
      </label>
      {consulting && (
        <p className="text-[11px] leading-4 text-w-dim">
          Espresso looks for businesses with a public reason to talk now (hiring a first HR person, an OSHA
          inspection, AI in hiring, a new location), writes to the decision-maker, and keeps each message under
          150 words with one ask: your booking link. It can't cite a number the research doesn't show or tell
          anyone they're breaking a law.
        </p>
      )}
      <label className={label}>
        Who to reach
        <textarea value={target} onChange={(e) => setTarget(e.target.value)} rows={3} maxLength={2000}
          placeholder={useHouse && house ? house.target : 'Dental practices in Texas with several locations'} className={input} />
      </label>
      <label className={label}>
        What you offer
        <textarea value={offer} onChange={(e) => setOffer(e.target.value)} rows={5} maxLength={4000}
          placeholder={useHouse && house ? house.offer : 'What you do, for whom, and the one thing you ask for'} className={input} />
      </label>
      {consulting && (
        <label className={label}>
          Booking link
          <input type="url" value={ctaUrl} onChange={(e) => setCtaUrl(e.target.value)} maxLength={2000}
            required={!useHouse} placeholder={useHouse && house ? house.cta_url : 'https://…'} className={input} />
        </label>
      )}
      <label className={label}>
        Footer
        <textarea value={footer} onChange={(e) => setFooter(e.target.value)} rows={2} maxLength={1000}
          placeholder={`Reply "unsubscribe" and I won't email you again.\n${FOOTER_PLACEHOLDER}`} className={input} />
        <span className="block font-normal text-w-faint">
          Every message ends with it: how to opt out and your business's postal address. Required to send.
        </span>
      </label>
      <div className="flex items-center gap-2">
        <button type="submit" disabled={busy || !title.trim()}
          className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
          {campaign ? 'Save' : 'Create campaign'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-xs text-w-dim hover:text-w-text">Cancel</button>
        )}
      </div>
    </form>
  )
}
