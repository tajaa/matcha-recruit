import type { DriveCap, DriveFolder, DriveSpace, DriveTree } from '../../../types'

export type DriveTreeNode = { folder: DriveFolder; children: DriveTreeNode[] }

/** Nest a flat folder list. A folder whose parent isn't in the list (the
 *  caller can't see it — e.g. an upload-only drop-box deep inside HR) becomes
 *  a root, so every visible folder is reachable. Siblings sort by name. */
export function buildDriveTree(folders: DriveFolder[]): DriveTreeNode[] {
  const byId = new Map<string, DriveTreeNode>()
  for (const folder of folders) byId.set(folder.id, { folder, children: [] })
  const roots: DriveTreeNode[] = []
  for (const node of byId.values()) {
    const parent = node.folder.parent_id ? byId.get(node.folder.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  const sort = (nodes: DriveTreeNode[]) => {
    nodes.sort((a, b) => a.folder.name.localeCompare(b.folder.name))
    nodes.forEach((n) => sort(n.children))
  }
  sort(roots)
  return roots
}

export function hasCap(caps: DriveCap[] | undefined, cap: DriveCap): boolean {
  return !!caps && caps.includes(cap)
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export const DRIVE_ACCEPT = '.pdf,.docx,.txt,.md,.csv,.xlsx,.png,.jpg,.jpeg'
export const DRIVE_MAX_BYTES = 25 * 1024 * 1024

/** Where a space opens: its root when visible, else its first visible folder
 *  (an upload-only grantee in HR has no root, just their drop-box). */
export function spaceEntry(tree: DriveTree, space: DriveSpace): string | null {
  const s = tree.spaces[space]
  if (!s?.visible) return null
  return s.folders.some((f) => f.id === s.root_folder_id) ? s.root_folder_id : s.folders[0]?.id ?? null
}
