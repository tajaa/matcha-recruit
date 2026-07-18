import type { Dispatch, SetStateAction } from 'react'
import { Loader2, Save } from 'lucide-react'
import ImageUpload from '../../components/ImageUpload'
import type { CappeSite } from '../../types'
import { DAY_LABELS, SOCIAL_FIELDS, type BizMeta } from './bizMeta'
import { inputCls } from './styles'

export function BusinessInfoSection({
  site, siteId, biz, setBiz, saving, onSave,
}: {
  site: CappeSite
  siteId: string
  biz: BizMeta
  setBiz: Dispatch<SetStateAction<BizMeta>>
  saving: boolean
  onSave: () => void
}) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
      <h2 className="mb-1 text-sm font-semibold text-zinc-100">Business info &amp; SEO</h2>
      <p className="mb-4 text-xs text-zinc-500">Shown in your site footer and used for search/social previews. All optional.</p>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Contact email</label>
            <input value={biz.contact_email} onChange={(e) => setBiz((b) => ({ ...b, contact_email: e.target.value }))} placeholder="hello@yourbusiness.com" className={inputCls} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Contact phone</label>
            <input value={biz.contact_phone} onChange={(e) => setBiz((b) => ({ ...b, contact_phone: e.target.value }))} placeholder="+1 555 123 4567" className={inputCls} />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Address</label>
          <input value={biz.contact_address} onChange={(e) => setBiz((b) => ({ ...b, contact_address: e.target.value }))} placeholder="123 Main St, City, ST" className={inputCls} />
          <p className="mt-1 text-xs text-zinc-500">Used by the Map / “Find us” block (with a Get-directions button).</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Latitude <span className="text-zinc-500">(optional — adds a map)</span></label>
            <input value={biz.lat} onChange={(e) => setBiz((b) => ({ ...b, lat: e.target.value }))} placeholder="37.7749" className={inputCls} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Longitude</label>
            <input value={biz.lng} onChange={(e) => setBiz((b) => ({ ...b, lng: e.target.value }))} placeholder="-122.4194" className={inputCls} />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Opening hours</label>
          <p className="mb-2 text-xs text-zinc-500">Powers the Hours block + a live “Open now” badge + search engines. (The free-text line below is a fallback.)</p>
          <div className="space-y-1.5">
            {biz.hours.map((h, i) => (
              <div key={h.day} className="flex items-center gap-2">
                <span className="w-10 text-xs text-zinc-400">{DAY_LABELS[h.day]}</span>
                <label className="flex items-center gap-1 text-xs text-zinc-500">
                  <input type="checkbox" checked={!h.closed} onChange={(e) => setBiz((b) => ({ ...b, hours: b.hours.map((x, j) => (j === i ? { ...x, closed: !e.target.checked } : x)) }))} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-900 text-emerald-500" /> Open
                </label>
                {!h.closed ? (
                  <>
                    <input type="time" value={h.open} onChange={(e) => setBiz((b) => ({ ...b, hours: b.hours.map((x, j) => (j === i ? { ...x, open: e.target.value } : x)) }))} className={`${inputCls} w-32`} />
                    <span className="text-zinc-500">–</span>
                    <input type="time" value={h.close} onChange={(e) => setBiz((b) => ({ ...b, hours: b.hours.map((x, j) => (j === i ? { ...x, close: e.target.value } : x)) }))} className={`${inputCls} w-32`} />
                  </>
                ) : <span className="text-xs text-zinc-600">Closed</span>}
              </div>
            ))}
          </div>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-zinc-300">Hours (free text — fallback)</label>
          <input value={biz.business_hours} onChange={(e) => setBiz((b) => ({ ...b, business_hours: e.target.value }))} placeholder="Mon–Fri 9am–5pm" className={inputCls} />
        </div>

        <div className="border-t border-zinc-800 pt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Social links</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {SOCIAL_FIELDS.map(({ key, label, ph }) => (
              <div key={key}>
                <label className="mb-1 block text-xs font-medium text-zinc-400">{label}</label>
                <input
                  value={biz.social[key]}
                  onChange={(e) => setBiz((b) => ({ ...b, social: { ...b.social, [key]: e.target.value } }))}
                  placeholder={ph}
                  className={inputCls}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-zinc-800 pt-4 space-y-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Search &amp; social preview (SEO)</p>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Page title</label>
            <input value={biz.seo.title} onChange={(e) => setBiz((b) => ({ ...b, seo: { ...b.seo, title: e.target.value } }))} placeholder={site.name} className={inputCls} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Description</label>
            <textarea value={biz.seo.description} onChange={(e) => setBiz((b) => ({ ...b, seo: { ...b.seo, description: e.target.value } }))} rows={2} placeholder="One or two sentences describing your business." className={inputCls} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Share image</label>
            <ImageUpload siteId={siteId || ''} value={biz.seo.og_image} onChange={(v) => setBiz((b) => ({ ...b, seo: { ...b.seo, og_image: v } }))} placeholder="Image shown when shared (1200×630)" />
          </div>
        </div>

        <div className="border-t border-zinc-800 pt-4">
          <label className="mb-1 block text-sm font-medium text-zinc-300">Favicon</label>
          <ImageUpload siteId={siteId || ''} value={biz.favicon_url} onChange={(v) => setBiz((b) => ({ ...b, favicon_url: v }))} placeholder="Browser-tab icon (square)" />
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
