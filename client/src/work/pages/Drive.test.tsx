import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DriveCap, DriveFolder, DriveFolderView, DriveTree } from '../types'
import Drive from './Drive'

const api = vi.hoisted(() => ({
  getDriveTree: vi.fn(),
  getDriveFolder: vi.fn(),
  createDriveFolder: vi.fn(),
  deleteDriveFile: vi.fn(),
  getDriveDownloadUrl: vi.fn(),
  searchDrive: vi.fn(),
  updateDriveFile: vi.fn(),
  uploadDriveFile: vi.fn(),
  listDriveGrants: vi.fn(),
  setDriveGrant: vi.fn(),
  removeDriveGrant: vi.fn(),
  searchDrivePeople: vi.fn(),
}))
vi.mock('../api/drive', () => api)

const ALL: DriveCap[] = ['list', 'read', 'add', 'manage', 'grant']

function folder(id: string, overrides: Partial<DriveFolder> = {}): DriveFolder {
  return {
    id, parent_id: null, space: 'general', name: id, system_key: null, is_system: false,
    caps: ALL, created_at: '2026-09-29T00:00:00Z', ...overrides,
  }
}

function tree(general: DriveFolder[], hr: DriveFolder[]): DriveTree {
  return {
    spaces: {
      general: { visible: general.length > 0, root_folder_id: 'company', folders: general },
      hr: { visible: hr.length > 0, root_folder_id: 'hr', folders: hr },
    },
  }
}

function folderView(f: DriveFolder, overrides: Partial<DriveFolderView> = {}): DriveFolderView {
  return { folder: f, breadcrumbs: [{ id: f.id, name: f.name }], folders: [], files: [], ...overrides }
}

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/work/drive" element={<><Drive /><Where /></>} />
        <Route path="/work/drive/:folderId" element={<><Drive /><Where /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
  api.searchDrive.mockResolvedValue({ results: [] })
})

describe('Drive', () => {
  it('opens the Company root when no folder is given', async () => {
    const company = folder('company', { name: 'Company', system_key: 'general_root', is_system: true })
    api.getDriveTree.mockResolvedValue(tree([company], []))
    api.getDriveFolder.mockResolvedValue(folderView(company, {
      files: [{
        id: 'f1', folder_id: 'company', filename: 'Handbook.pdf', content_type: 'application/pdf',
        file_size: 2048, text_status: 'ok', source: 'upload', linked_type: null, linked_id: null,
        uploaded_by: null, created_at: '2026-09-29T00:00:00Z', updated_at: '2026-09-29T00:00:00Z',
      }],
    }))
    renderAt('/work/drive')
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/work/drive/company'))
    expect(await screen.findByText('Handbook.pdf')).toBeTruthy()
    // HR isn't visible to this user, so there is no HR tab.
    expect(screen.queryByRole('tab', { name: 'HR' })).toBeNull()
    expect(screen.getByRole('tab', { name: 'Company' })).toBeTruthy()
  })

  it('shows only a drop target in an upload-only folder', async () => {
    const drafts = folder('drafts', { space: 'hr', name: 'Drafts', parent_id: 'discipline', caps: ['add'] })
    api.getDriveTree.mockResolvedValue(tree([], [drafts]))
    api.getDriveFolder.mockResolvedValue(folderView(drafts, { breadcrumbs: [] }))
    api.uploadDriveFile.mockResolvedValue({})
    renderAt('/work/drive')
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/work/drive/drafts'))
    expect(await screen.findByText(/Only the people who manage it can see them/)).toBeTruthy()
    expect(screen.queryByText('This folder is empty.')).toBeNull()
    expect(screen.queryByRole('button', { name: /Share/ })).toBeNull()

    const input = screen.getByTestId('drive-file-input') as HTMLInputElement
    const file = new File(['draft'], 'write-up.pdf', { type: 'application/pdf' })
    fireEvent.change(input, { target: { files: [file] } })
    expect(await screen.findByText('Sent 1 file to Drafts.')).toBeTruthy()
    expect(api.uploadDriveFile).toHaveBeenCalledWith('drafts', file)
    // A drop-box never re-lists the folder after an upload.
    expect(api.getDriveFolder).toHaveBeenCalledTimes(1)
  })

  it('rejects files over 25 MB without uploading them', async () => {
    const company = folder('company', { name: 'Company' })
    api.getDriveTree.mockResolvedValue(tree([company], []))
    api.getDriveFolder.mockResolvedValue(folderView(company))
    renderAt('/work/drive/company')
    await screen.findByText('This folder is empty.')
    const big = new File(['x'], 'huge.pdf', { type: 'application/pdf' })
    Object.defineProperty(big, 'size', { value: 26 * 1024 * 1024 })
    fireEvent.change(screen.getByTestId('drive-file-input'), { target: { files: [big] } })
    expect(await screen.findByText(/huge\.pdf \(over 25 MB\)/)).toBeTruthy()
    expect(api.uploadDriveFile).not.toHaveBeenCalled()
  })

  it('hides manage actions without the manage capability', async () => {
    const company = folder('company', { name: 'Company', caps: ['list', 'read'] })
    api.getDriveTree.mockResolvedValue(tree([company], []))
    api.getDriveFolder.mockResolvedValue(folderView(company))
    renderAt('/work/drive/company')
    await screen.findByText('This folder is empty.')
    expect(screen.queryByRole('button', { name: /New folder/ })).toBeNull()
    expect(screen.queryByText(/Drop files here/)).toBeNull()
  })

  it('creates a folder in the open folder', async () => {
    const company = folder('company', { name: 'Company' })
    api.getDriveTree.mockResolvedValue(tree([company], []))
    api.getDriveFolder.mockResolvedValue(folderView(company))
    api.createDriveFolder.mockResolvedValue(folder('policies', { parent_id: 'company' }))
    renderAt('/work/drive/company')
    fireEvent.click(await screen.findByRole('button', { name: /New folder/ }))
    fireEvent.change(screen.getByLabelText('New folder name'), { target: { value: ' Policies ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(api.createDriveFolder).toHaveBeenCalledWith('company', 'Policies'))
  })

  it('shows a folder error instead of spinning forever', async () => {
    api.getDriveTree.mockResolvedValue(tree([folder('company')], []))
    api.getDriveFolder.mockRejectedValue(new Error("That folder doesn't exist."))
    renderAt('/work/drive/missing')
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', "That folder doesn't exist.")
  })

  it('tells people with no access to ask an admin', async () => {
    api.getDriveTree.mockResolvedValue(tree([], []))
    renderAt('/work/drive')
    expect(await screen.findByText(/don't have access to any Drive folders/)).toBeTruthy()
  })

  it('searches after two characters and shows results', async () => {
    const company = folder('company', { name: 'Company' })
    api.getDriveTree.mockResolvedValue(tree([company], []))
    api.getDriveFolder.mockResolvedValue(folderView(company))
    api.searchDrive.mockResolvedValue({
      results: [{
        id: 'f9', folder_id: 'company', filename: 'Leave policy.pdf', content_type: null, file_size: 1,
        text_status: 'ok', source: 'upload', linked_type: null, linked_id: null, uploaded_by: null,
        created_at: '2026-09-29T00:00:00Z', updated_at: '2026-09-29T00:00:00Z',
        folder_name: 'Company', space: 'general',
      }],
    })
    renderAt('/work/drive/company')
    await screen.findByText('This folder is empty.')
    fireEvent.change(screen.getByLabelText('Search files'), { target: { value: 'l' } })
    expect(api.searchDrive).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Search files'), { target: { value: 'leave' } })
    expect(await screen.findByText('Leave policy.pdf')).toBeTruthy()
    expect(api.searchDrive).toHaveBeenCalledWith('leave')
  })
})
