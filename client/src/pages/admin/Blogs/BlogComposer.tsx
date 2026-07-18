import { type Dispatch, type SetStateAction } from 'react'
import { Loader2, ArrowLeft } from 'lucide-react'
import { api } from '../../../api/client'
import { slugify } from './slugify'
import { useComposer } from './useComposer'
import type { BlogPost } from './types'

export default function BlogComposer({
  isComposer, setPosts, load,
}: {
  isComposer: boolean
  setPosts: Dispatch<SetStateAction<BlogPost[]>>
  load: () => void | Promise<void>
}) {
  const {
    navigate,
    composeTitle, setComposeTitle,
    composeSlug, setComposeSlug,
    composeContent, setComposeContent,
    composeExcerpt, setComposeExcerpt,
    composeCover, setComposeCover,
    composeTags, setComposeTags,
    composeMetaTitle, setComposeMetaTitle,
    composeMetaDesc, setComposeMetaDesc,
    autoSlug, setAutoSlug,
    isDirty, saveStatus, composeId, composeSaving,
    publishCompose, uploadCover, mark,
  } = useComposer({ isComposer, setPosts, load })

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => {
            if (isDirty && !confirm('Discard unsaved changes?')) return
            navigate('/admin/blogs')
          }}
          className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1 text-xs"
        >
          <ArrowLeft size={14} /> Posts
        </button>
        <span className="text-zinc-700">/</span>
        <span className="text-xs text-zinc-400">New post</span>
        <div className="ml-auto h-4 flex items-center">
          {saveStatus === 'saving' && <span className="text-[10px] text-zinc-500 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Saving…</span>}
          {saveStatus === 'saved' && composeId && <span className="text-[10px] text-zinc-500">Draft saved</span>}
          {saveStatus === 'unsaved' && <span className="text-[10px] text-amber-500">Unsaved changes</span>}
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <label className="text-[10px] uppercase tracking-wider text-zinc-500">Title</label>
          <input
            type="text"
            value={composeTitle}
            onChange={e => { setComposeTitle(e.target.value); mark() }}
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-lg text-zinc-100 mt-1 font-semibold"
            placeholder="Post title…"
            autoFocus
          />
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-zinc-500 flex items-center justify-between">
            <span>Slug (/blog/&lt;slug&gt;)</span>
            <label className="flex items-center gap-1 normal-case text-zinc-400 font-normal cursor-pointer">
              <input type="checkbox" checked={autoSlug} onChange={e => setAutoSlug(e.target.checked)} />
              <span>Auto from title</span>
            </label>
          </label>
          <input
            type="text"
            value={composeSlug}
            onChange={e => { setComposeSlug(slugify(e.target.value)); setAutoSlug(false); mark() }}
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono mt-1"
            placeholder="my-post-slug"
          />
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-zinc-500">Excerpt (optional, ~160 chars)</label>
          <textarea
            value={composeExcerpt}
            onChange={e => { setComposeExcerpt(e.target.value); mark() }}
            rows={2}
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1 resize-none"
            placeholder="One-line summary shown on blog index"
          />
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-zinc-500">Cover image</label>
          <div className="flex items-center gap-2 mt-1">
            <input
              type="text"
              value={composeCover}
              onChange={e => { setComposeCover(e.target.value); mark() }}
              className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono"
              placeholder="https://…"
            />
            <label className="bg-zinc-800 hover:bg-zinc-700 px-3 py-2 text-xs text-zinc-300 rounded cursor-pointer">
              Upload
              <input type="file" accept="image/*" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) uploadCover(f) }} />
            </label>
          </div>
          {composeCover && <img src={composeCover} alt="cover preview" className="mt-2 h-32 object-cover rounded border border-zinc-800" />}
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Content (markdown)</label>
            <label className="text-[10px] text-zinc-400 hover:text-zinc-200 cursor-pointer">
              Insert image
              <input type="file" accept="image/*" className="hidden" onChange={async e => {
                const f = e.target.files?.[0]; if (!f) return
                const fd = new FormData(); fd.append('file', f)
                try {
                  const res = await api.upload<{ url: string }>('/blogs/upload', fd)
                  setComposeContent(c => `${c}\n\n![${f.name}](${res.url})\n`)
                  mark()
                } catch {}
              }} />
            </label>
          </div>
          <textarea
            value={composeContent}
            onChange={e => { setComposeContent(e.target.value); mark() }}
            rows={20}
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 font-mono"
            placeholder={'# Heading\n\nParagraph text…'}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Tags (comma-separated)</label>
            <input
              type="text"
              value={composeTags}
              onChange={e => { setComposeTags(e.target.value); mark() }}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
              placeholder="hr, compliance"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta title (SEO)</label>
            <input
              type="text"
              value={composeMetaTitle}
              onChange={e => { setComposeMetaTitle(e.target.value); mark() }}
              className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
            />
          </div>
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-zinc-500">Meta description (SEO)</label>
          <input
            type="text"
            value={composeMetaDesc}
            onChange={e => { setComposeMetaDesc(e.target.value); mark() }}
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 mt-1"
          />
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={publishCompose}
            disabled={composeSaving || !composeTitle.trim()}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium rounded"
          >
            {composeSaving ? 'Publishing…' : 'Publish'}
          </button>
          <button
            onClick={() => { if (isDirty && !confirm('Discard unsaved changes?')) return; navigate('/admin/blogs') }}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          >
            Back to drafts
          </button>
        </div>
      </div>
    </div>
  )
}
