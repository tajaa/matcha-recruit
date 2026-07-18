import { Hash, FolderOpen, MessageSquare, Plus, X } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import type { OpenTab } from './types'

const tabIcon = { channel: Hash, project: FolderOpen, thread: MessageSquare } as const

interface Props {
  openTabs: OpenTab[]
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  openTabPath: (tab: OpenTab) => string
  closeTab: (e: React.MouseEvent, tab: OpenTab) => void
}

// Tabs — recently/currently opened items, browser-tab style
export default function SidebarTabs({ openTabs, base, navigate, isActive, openTabPath, closeTab }: Props) {
  if (openTabs.length === 0) return null
  return (
    <div className="mb-1">
      <div className="flex items-center justify-between px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-w-faint">
        Tabs
        <button onClick={() => navigate(base)} className="hover:text-w-accent" title="New tab">
          <Plus size={11} />
        </button>
      </div>
      <div className="space-y-0.5">
        {openTabs.map((t) => {
          const Icon = tabIcon[t.type]
          const active = isActive(openTabPath(t))
          return (
            <div
              key={`${t.type}-${t.id}`}
              onClick={() => navigate(openTabPath(t))}
              className={`group w-full flex items-center gap-2 px-2.5 py-1 rounded-md text-[12px] cursor-pointer transition-colors ${
                active ? 'bg-w-surface2 text-white font-medium' : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
            >
              <Icon size={12} className="shrink-0" />
              <span className="flex-1 min-w-0 truncate">{t.label}</span>
              <button
                onClick={(e) => closeTab(e, t)}
                className="shrink-0 opacity-0 group-hover:opacity-100 p-0.5 text-w-faint hover:text-w-text transition-all"
                title="Close tab"
              >
                <X size={10} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
