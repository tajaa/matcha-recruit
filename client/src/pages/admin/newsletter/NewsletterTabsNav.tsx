import type { Newsletter, Tab } from './types'

type Props = {
  tab: Tab
  editingId: string | null
  newsletters: Newsletter[]
  onTabChange: (next: Tab) => void
}

export function NewsletterTabsNav({ tab, editingId, newsletters, onTabChange }: Props) {
  return (
    <div className="flex gap-1 mb-6 border-b border-white/[0.06] pb-px">
      {(['ideas', 'subscribers', 'newsletters', 'compose', 'tags', 'templates'] as Tab[]).map((t) => {
        const draftCount = t === 'newsletters' ? newsletters.filter(n => n.status === 'draft').length : 0
        return (
          <button key={t} onClick={() => onTabChange(t)} className={`px-4 py-2 text-xs font-medium transition-colors relative flex items-center gap-1.5 ${tab === t ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
            {t === 'compose' ? (editingId ? 'Edit Draft' : 'Compose') : t.charAt(0).toUpperCase() + t.slice(1)}
            {draftCount > 0 && (
              <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-zinc-700 text-zinc-300 font-mono leading-none">{draftCount}</span>
            )}
            {tab === t && <span className="absolute bottom-0 left-2 right-2 h-px bg-zinc-300 rounded-full" />}
          </button>
        )
      })}
    </div>
  )
}
