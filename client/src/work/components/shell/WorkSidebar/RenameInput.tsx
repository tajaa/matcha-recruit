import type { SidebarRename } from './useSidebarRename'

// ─── Inline rename input ───
export default function RenameInput({ rename }: { rename: SidebarRename }) {
  const { renameRef, renameDraft, setRenameDraft, submitRename, setRenaming } = rename
  return (
    <div className="flex items-center gap-1 px-1 flex-1 min-w-0">
      <input
        ref={renameRef}
        value={renameDraft}
        onChange={(e) => setRenameDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') submitRename()
          if (e.key === 'Escape') setRenaming(null)
        }}
        onBlur={submitRename}
        className="flex-1 min-w-0 rounded border border-w-line bg-w-surface2 px-1.5 py-0.5 text-[13px] text-w-text outline-none focus:border-w-accent"
      />
    </div>
  )
}
