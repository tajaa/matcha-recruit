import { Loader2, Plus, Send, Tag as TagIcon, Calendar, Blocks, Code2 } from 'lucide-react'
import SectionEditor from '../../../components/matcha-work/SectionEditor'
import { Button } from '../../../components/ui/Button'
import { LABEL } from '../../../components/ui/typography'
import { MobilePreview, type ViewportKey } from './MobilePreview'
import { uploadNewsletterMedia } from './uploadMedia'
import { NewsletterBuilder } from './blocks/NewsletterBuilder'
import { emptyDesign, type NewsletterDesign } from './blocks/schema'

export type ComposeMode = 'design' | 'html'

export function ComposeTab({
  saveStatus,
  editingId,
  composeTitle, setComposeTitle,
  composeSubject, setComposeSubject,
  composePreheader, setComposePreheader,
  composeHtml, setComposeHtml,
  composeMode, setComposeMode,
  composeDesign, setComposeDesign,
  setIsDirty, setSaveStatus,
  previewViewport, setPreviewViewport,
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
  composeMode: ComposeMode; setComposeMode: (v: ComposeMode) => void
  composeDesign: NewsletterDesign | null; setComposeDesign: (v: NewsletterDesign) => void
  setIsDirty: (v: boolean) => void
  setSaveStatus: (v: 'saved' | 'saving' | 'unsaved') => void
  previewViewport: ViewportKey; setPreviewViewport: (v: ViewportKey) => void
  saving: boolean
  handleCreate: () => Promise<void>
  handleSave: () => Promise<void>
  handleTestSend: () => Promise<void>
  openSend: (kind: 'now' | 'schedule' | 'segment') => Promise<void>
}) {
  const design = composeDesign ?? emptyDesign('light')
  const markDirty = () => { setIsDirty(true); setSaveStatus('unsaved') }
  return (
    <div className="space-y-4">
      {/* Save status indicator */}
      <div className="h-4 flex items-center">
        {saveStatus === 'saving' && <span className="text-[10px] text-zinc-500 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Saving…</span>}
        {saveStatus === 'saved' && editingId && <span className="text-[10px] text-zinc-500">Saved</span>}
        {saveStatus === 'unsaved' && <span className="text-[10px] text-amber-500">Unsaved changes</span>}
      </div>
      <div className={`grid ${previewViewport === 'wide' ? 'grid-cols-1' : previewViewport === 'desktop' ? 'lg:grid-cols-[1fr_660px]' : 'lg:grid-cols-[1fr_376px]'} gap-6 max-w-6xl`}>
        <div className="space-y-4">
          <div>
            <label className={`block ${LABEL} mb-1.5`}>Title</label>
            <input value={composeTitle} onChange={(e) => { setComposeTitle(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} placeholder="Newsletter title..." className="w-full px-3 py-2 rounded-lg border border-white/[0.08] bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
          </div>
          <div>
            <label className={`block ${LABEL} mb-1.5`}>Subject line</label>
            <input value={composeSubject} onChange={(e) => { setComposeSubject(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} placeholder="Email subject..." className="w-full px-3 py-2 rounded-lg border border-white/[0.08] bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
          </div>
          <div>
            <label className={`block ${LABEL} mb-1.5`}>
              Preheader <span className="normal-case tracking-normal text-zinc-600">— inbox preview snippet, hidden in body</span>
            </label>
            <input value={composePreheader} onChange={(e) => { setComposePreheader(e.target.value); setIsDirty(true); setSaveStatus('unsaved') }} maxLength={255} placeholder="Short hook seen in the recipient's inbox preview..." className="w-full px-3 py-2 rounded-lg border border-white/[0.08] bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500" />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className={LABEL}>Content</label>
              {/* Design (block builder) vs raw HTML editor */}
              <div className="flex items-center gap-1 rounded-lg bg-zinc-900 border border-white/[0.06] p-0.5">
                <button
                  type="button"
                  onClick={() => setComposeMode('design')}
                  className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded-md ${composeMode === 'design' ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}
                >
                  <Blocks size={12} /> Design
                </button>
                <button
                  type="button"
                  onClick={() => setComposeMode('html')}
                  className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded-md ${composeMode === 'html' ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}
                >
                  <Code2 size={12} /> HTML
                </button>
              </div>
            </div>
            {composeMode === 'design' ? (
              <NewsletterBuilder
                design={design}
                onChange={(next) => { setComposeDesign(next); markDirty() }}
              />
            ) : (
              <div className="rounded-lg border border-white/[0.06] bg-zinc-950 overflow-hidden">
                <SectionEditor
                  content={composeHtml}
                  onUpdate={(html) => { setComposeHtml(html); setIsDirty(true); setSaveStatus('unsaved') }}
                  onImageUpload={uploadNewsletterMedia}
                  onVideoUpload={uploadNewsletterMedia}
                />
              </div>
            )}
          </div>
        </div>

        {/* Preview pane */}
        <MobilePreview
          title={composeTitle}
          subject={composeSubject}
          preheader={composePreheader}
          html={composeHtml}
          designJson={composeMode === 'design' ? design : null}
          defaultTheme={composeMode === 'design' ? design.theme.preset : undefined}
          viewport={previewViewport}
          onViewportChange={setPreviewViewport}
        />
      </div>

      <div className="flex flex-wrap gap-2 max-w-6xl">
        {!editingId ? (
          <Button onClick={handleCreate} disabled={saving || !composeTitle.trim() || !composeSubject.trim()} variant="secondary" size="md">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Create Draft
          </Button>
        ) : (
          <>
            <Button onClick={handleSave} disabled={saving} variant="secondary" size="md">
              {saving ? <Loader2 size={14} className="animate-spin" /> : null} Save Draft
            </Button>
            <Button onClick={handleTestSend} variant="ghost" size="md" className="border border-white/[0.08]">
              <Send size={14} /> Send Test
            </Button>
            <button onClick={() => openSend('now')} className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg">
              <Send size={14} /> Send to all
            </button>
            <button onClick={() => openSend('segment')} className="flex items-center gap-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium rounded-lg">
              <TagIcon size={14} /> Send to segment
            </button>
            <button onClick={() => openSend('schedule')} className="flex items-center gap-1.5 px-4 py-2 bg-sky-700 hover:bg-sky-600 text-white text-sm font-medium rounded-lg">
              <Calendar size={14} /> Schedule…
            </button>
          </>
        )}
      </div>
    </div>
  )
}
