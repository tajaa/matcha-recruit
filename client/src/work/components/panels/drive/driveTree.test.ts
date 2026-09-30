import { describe, expect, it } from 'vitest'
import type { DriveFolder, DriveTree } from '../../../types'
import { buildDriveTree, formatBytes, spaceEntry } from './driveTree'

function folder(id: string, parent_id: string | null, name = id): DriveFolder {
  return { id, parent_id, space: 'hr', name, system_key: null, is_system: false, caps: ['list'], created_at: '' }
}

describe('buildDriveTree', () => {
  it('nests children and sorts siblings by name', () => {
    const roots = buildDriveTree([folder('hr', null, 'HR'), folder('b', 'hr', 'Templates'), folder('a', 'hr', 'Discipline')])
    expect(roots).toHaveLength(1)
    expect(roots[0].children.map((c) => c.folder.name)).toEqual(['Discipline', 'Templates'])
  })

  it('treats a folder with an invisible parent as a root', () => {
    const roots = buildDriveTree([folder('drafts', 'discipline', 'Drafts')])
    expect(roots.map((r) => r.folder.id)).toEqual(['drafts'])
  })
})

describe('spaceEntry', () => {
  const t = (folders: DriveFolder[], visible = true): DriveTree => ({
    spaces: {
      general: { visible: false, root_folder_id: 'company', folders: [] },
      hr: { visible, root_folder_id: 'hr', folders },
    },
  })

  it('prefers the root, falls back to the first visible folder, else null', () => {
    expect(spaceEntry(t([folder('hr', null), folder('x', 'hr')]), 'hr')).toBe('hr')
    expect(spaceEntry(t([folder('drafts', 'discipline')]), 'hr')).toBe('drafts')
    expect(spaceEntry(t([], false), 'hr')).toBeNull()
    expect(spaceEntry(t([]), 'general')).toBeNull()
  })
})

describe('formatBytes', () => {
  it('formats sizes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(50 * 1024)).toBe('50 KB')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})
