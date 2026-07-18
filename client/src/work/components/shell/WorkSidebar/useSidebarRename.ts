import { useEffect, useRef, useState } from 'react'
import { updateChannel } from '../../../api/channels'
import type { ChannelSummary } from '../../../api/channels'
import { updateTitle, updateProjectMeta } from '../../../api/matchaWork'
import type { MWThread, MWProject } from '../../../types'
import type { RenameItem } from './types'

type Args = {
  setChannels: React.Dispatch<React.SetStateAction<ChannelSummary[]>>
  setProjects: React.Dispatch<React.SetStateAction<MWProject[]>>
  setThreads: React.Dispatch<React.SetStateAction<MWThread[]>>
}

/** Inline rename state + persistence for channels / projects / threads. */
export function useSidebarRename({ setChannels, setProjects, setThreads }: Args) {
  const [renaming, setRenaming] = useState<RenameItem | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const renameRef = useRef<HTMLInputElement>(null)

  // Focus rename input when it appears
  useEffect(() => {
    if (renaming) renameRef.current?.focus()
  }, [renaming])

  function startRename(type: RenameItem['type'], id: string, name: string) {
    setRenaming({ type: type!, id, name })
    setRenameDraft(name)
  }

  async function submitRename() {
    if (!renaming || !renameDraft.trim() || renameDraft.trim() === renaming.name) {
      setRenaming(null)
      return
    }
    const newName = renameDraft.trim()
    try {
      if (renaming.type === 'channel') {
        await updateChannel(renaming.id, { name: newName })
        setChannels((prev) => prev.map((ch) => ch.id === renaming.id ? { ...ch, name: newName, slug: newName.toLowerCase().replace(/[^a-z0-9]+/g, '-') } : ch))
      } else if (renaming.type === 'project') {
        await updateProjectMeta(renaming.id, { title: newName })
        setProjects((prev) => prev.map((p) => p.id === renaming.id ? { ...p, title: newName } : p))
      } else if (renaming.type === 'thread') {
        await updateTitle(renaming.id, newName)
        setThreads((prev) => prev.map((t) => t.id === renaming.id ? { ...t, title: newName } : t))
      }
    } catch {}
    setRenaming(null)
  }

  return { renaming, setRenaming, renameDraft, setRenameDraft, renameRef, startRename, submitRename }
}

export type SidebarRename = ReturnType<typeof useSidebarRename>
