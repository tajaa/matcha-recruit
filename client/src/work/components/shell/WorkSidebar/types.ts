export interface Props {
  open: boolean
  onToggle: () => void
}

export type RenameItem = { type: 'channel' | 'project' | 'thread'; id: string; name: string }
