import { Loader2, Plus, Send, Tag as TagIcon, Calendar, Palette } from 'lucide-react'
import SectionEditor from '../../../components/matcha-work/SectionEditor'
import { MobilePreview } from './MobilePreview'
import { uploadNewsletterMedia } from './uploadMedia'

// Quick-pick swatches — a small curated set, not a full color picker. Admins
// can still type any hex value in the field next to it.
const ACCENT_PRESETS = [
  { label: 'Emerald', value: '#059669' },
  { label: 'Sky', value: '#0284c7' },
  { label: 'Amber', value: '#d97706' },
  { label: 'Rose', value: '#e11d48' },
  { label: 'Violet', value: '#7c3aed' },
  { label: 'Slate', value: '#334155' },
]

export function ComposeTab({
  saveStatus,
  editingId,
  composeTitle, setComposeTitle,
  composeSubject, setComposeSubject,
  composePreheader, setComposePreheader,
  composeHtml, setComposeHtml,
  composeTheme, setComposeTheme,
  composeAccentColor, setComposeAccentColor,
  setIsDirty, setSaveStatus,
  saving,
  handleCreate,
  handleSave,
  handleTestSend,
  openSend,
}: {
  saveStatus: 'saved' | 'saving' | 'unsaved'
  editingId: string | null
  composeTitle: string; setComposeTitle: (v: string) => void
  composeSubject: string; setComposeSubject: (v: string) => void
  composePreheader: string; setComposePreheader: (v: string) => void
  composeHtml: string; setComposeHtml: (v: string) => void
  composeTheme: 'dark' | 'light'; setComposeTheme: (v: 'dark' | 'light') => void
  composeAccentColor: string; setComposeAccentColor: (v: string) => void
  setIsDirty: (v: boolean) => void
  setSaveStatus: (v: 'saved' | 'saving' | 'unsaved') => void
  saving: boolean
  handleCreate: () => Promise<void>
  handleSave: () => Promise<void>
  handleTestSend: () => Promise<void>
  openSend: (kind: 'now' | 'schedule' | 'segment') => Promise<void>
}) {
  const isValidHex = /^#[0-9A-Fa-f]{6}$/.test(composeAccentColor)
  return (
    <div className="space-y-4">
      {/* Save status indicator */}
      <div className="h-4 flex items-center">
        {saveStatus === 'saving' && <span className="text-[10px] text-slate-400 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Saving…</span>}
        {saveStatus === 'saved' && editingId && <span className="text-[10px] text-slate-400">Saved</span>}
        {saveStatus === 'unsaved' && <span className="text-[10px] text-amber-600">Unsaved changes</span>}
      </div>
      <div className="grid lg:grid-cols-[1fr_660px] gap-6 max-w-6xl">
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-slate-600 mb-1">Title</label>
            <input value={composeTitle} onChange={(e) => { setComposeTitle(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} placeholder="Newsletter title..." className="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition-colors" />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Subject line</label>
            <input value={composeSubject} onChange={(e) => { setComposeSubject(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} placeholder="Email subject..." className="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition-colors" />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">
              Preheader <span className="text-slate-400">— inbox preview snippet, hidden in body</span>
            </label>
            <input value={composePreheader} onChange={(e) => { setComposePreheader(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} maxLength={255} placeholder="Short hook seen in the recipient's inbox preview..." className="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition-colors" />
          </div>
          <div className="rounded-lg border border-slate-200 bg-white shadow-sm p-3">
            <p className="text-xs font-medium text-slate-700 mb-2.5 flex items-center gap-1.5"><Palette size={13} className="text-slate-400" /> Design settings</p>
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
              <div>
                <label className="block text-[10px] text-slate-500 uppercase tracking-wide mb-1">Theme</label>
                <div className="flex gap-1">
                  {(['light', 'dark'] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => { setComposeTheme(t); setIsDirty(true); setSaveStatus('unsaved') }}
                      className={`text-xs px-3 py-1.5 rounded-lg border ${composeTheme === t ? 'bg-slate-800 border-slate-800 text-white' : 'bg-white border-slate-300 text-slate-600 hover:bg-slate-50'}`}
                    >
                      {t === 'dark' ? 'Dark' : 'Light'}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-[10px] text-slate-500 uppercase tracking-wide mb-1">Accent color</label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="color"
                    value={isValidHex ? composeAccentColor : '#059669'}
                    onChange={(e) => { setComposeAccentColor(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }}
                    className="w-8 h-8 rounded border border-slate-300 cursor-pointer bg-white p-0.5"
                    title="Pick accent color"
                  />
                  <input
                    value={composeAccentColor}
                    onChange={(e) => { setComposeAccentColor(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }}
                    placeholder="#059669"
                    maxLength={7}
                    className={`w-24 px-2 py-1.5 rounded-lg border text-xs font-mono outline-none focus:ring-2 focus:ring-emerald-500/20 ${isValidHex ? 'border-slate-300 text-slate-800 focus:border-emerald-500' : 'border-red-300 text-red-600 focus:border-red-400'}`}
                  />
                </div>
              </div>
              <div>
                <label className="block text-[10px] text-slate-500 uppercase tracking-wide mb-1">Presets</label>
                <div className="flex items-center gap-1.5">
                  {ACCENT_PRESETS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => { setComposeAccentColor(p.value); setIsDirty(true); setSaveStatus('unsaved') }}
                      title={p.label}
                      style={{ background: p.value }}
                      className={`w-6 h-6 rounded-full border-2 transition-transform hover:scale-110 ${composeAccentColor.toLowerCase() === p.value ? 'border-slate-800' : 'border-white shadow-sm'}`}
                    />
                  ))}
                </div>
              </div>
            </div>
            {!isValidHex && <p className="text-[10px] text-red-600 mt-2">Accent color must be a 6-digit hex value, e.g. #059669.</p>}
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Content</label>
            <div className="rounded-lg border border-slate-300 overflow-hidden shadow-sm" style={{ background: '#1e1e1e' }}>
              <SectionEditor
                content={composeHtml}
                onUpdate={(html) => { setComposeHtml(html); setIsDirty(true); setSaveStatus('unsaved') }}
                onImageUpload={uploadNewsletterMedia}
                onVideoUpload={uploadNewsletterMedia}
              />
            </div>
          </div>
        </div>

        {/* Preview pane — desktop + mobile shown together, reflects Design settings live */}
        <MobilePreview
          title={composeTitle}
          subject={composeSubject}
          preheader={composePreheader}
          html={composeHtml}
          theme={composeTheme}
          accentColor={isValidHex ? composeAccentColor : '#059669'}
        />
      </div>

      <div className="flex flex-wrap gap-2 max-w-6xl">
        {!editingId ? (
          <button onClick={handleCreate} disabled={saving || !composeTitle.trim() || !composeSubject.trim()} className="flex items-center gap-1.5 px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-lg shadow-sm disabled:opacity-40">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Create Draft
          </button>
        ) : (
          <>
            <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-lg shadow-sm disabled:opacity-40">
              {saving ? <Loader2 size={14} className="animate-spin" /> : null} Save Draft
            </button>
            <button onClick={handleTestSend} className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium rounded-lg border border-slate-300 shadow-sm">
              <Send size={14} /> Send Test
            </button>
            <button onClick={() => openSend('now')} className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg shadow-sm">
              <Send size={14} /> Send to all
            </button>
            <button onClick={() => openSend('segment')} className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-emerald-50 text-emerald-700 text-sm font-medium rounded-lg border border-emerald-300 shadow-sm">
              <TagIcon size={14} /> Send to segment
            </button>
            <button onClick={() => openSend('schedule')} className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-sky-50 text-sky-700 text-sm font-medium rounded-lg border border-sky-300 shadow-sm">
              <Calendar size={14} /> Schedule…
            </button>
          </>
        )}
      </div>
    </div>
  )
}
