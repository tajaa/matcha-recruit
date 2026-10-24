import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../../api/client'
import { ToastProvider } from '../../../../components/ui'
import type { CappeStudioBankItem } from '../../../../types/cappeAdmin'
import CappeStudioBank from './CappeStudioBank'

const item = (over: Partial<CappeStudioBankItem> = {}): CappeStudioBankItem => ({
  id: 'p1', kind: 'photo', name: 'Harbour at dawn', tags: ['sea'], collection: 'Coast', status: 'live', sort_order: 0,
  url: 'https://cdn.example.test/b.jpg', variants: null, width: 1600, height: 1000, creator: 'Ana Ruiz',
  credit_line: 'Ana Ruiz / Gummfit', license: 'gummfit', source_url: null, sha: null, mono: null, fit: null,
  graphic_group: null, created_by_email: 'admin@example.com', created_at: '2026-10-22T10:00:00Z', ...over,
})
const wave = item({ id: 'g1', kind: 'graphic', name: 'Wave', url: null, credit_line: null, license: null, creator: null,
  sha: 'e'.repeat(64), mono: true, fit: 'stretch', graphic_group: 'lines' })

const show = () => render(<ToastProvider><CappeStudioBank /></ToastProvider>)

beforeEach(() => vi.restoreAllMocks())

describe('the Studio bank admin', () => {
  it('lists the photos, and hides and deletes one', async () => {
    vi.spyOn(api, 'get').mockResolvedValue([item()])
    const patch = vi.spyOn(api, 'patch').mockResolvedValue(item({ status: 'hidden' }))
    const del = vi.spyOn(api, 'delete').mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    show()
    const row = (await screen.findByText('Harbour at dawn')).closest('tr')!
    expect(within(row).getByText('Ana Ruiz / Gummfit')).toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: 'Actions for Harbour at dawn' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Hide' }))
    await waitFor(() => expect(within(row).getByText('Hidden')).toBeInTheDocument())
    expect(patch).toHaveBeenCalledWith('/cappe/matcha-admin/studio-bank/p1', { status: 'hidden' })
    fireEvent.click(within(row).getByRole('button', { name: 'Actions for Harbour at dawn' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))
    await waitFor(() => expect(screen.queryByText('Harbour at dawn')).not.toBeInTheDocument())
    expect(del).toHaveBeenCalledWith('/cappe/matcha-admin/studio-bank/p1')
  })

  it('adds a graphic, which can be hidden but not deleted', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue([])
    const upload = vi.spyOn(api, 'upload').mockResolvedValue(wave)
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Graphics' }))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/cappe/matcha-admin/studio-bank?kind=graphic'))
    const file = new File(['<svg/>'], 'wave.svg', { type: 'image/svg+xml' })
    fireEvent.change(screen.getByLabelText('SVG file'), { target: { files: [file] } })
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Wave' } })
    fireEvent.change(screen.getByLabelText('Kind of graphic'), { target: { value: 'lines' } })
    fireEvent.submit(screen.getByRole('button', { name: 'Add to the bank' }).closest('form')!) // jsdom can't see a test's file as `required` met
    await waitFor(() => expect(upload).toHaveBeenCalled())
    const [path, form] = upload.mock.calls[0] as [string, FormData]
    expect(path).toBe('/cappe/matcha-admin/studio-bank/graphics')
    expect([form.get('name'), form.get('group'), form.get('colour'), (form.get('file') as File).name]).toEqual(['Wave', 'lines', 'auto', 'wave.svg'])
    const row = (await screen.findByText('Wave')).closest('tr')!
    expect(within(row).getByText('Line or divider, one colour')).toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: 'Actions for Wave' }))
    expect(screen.getByRole('menuitem', { name: 'Hide' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('keeps a photo upload that finishes after switching to graphics out of the graphics list', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue([])
    let finish!: (i: CappeStudioBankItem) => void
    vi.spyOn(api, 'upload').mockImplementation(() => new Promise((res) => { finish = res as typeof finish }))
    show()
    const file = new File(['JPEG'], 'b.jpg', { type: 'image/jpeg' })
    fireEvent.change(await screen.findByLabelText('Photo (JPEG, PNG, WebP)'), { target: { files: [file] } })
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Harbour at dawn' } })
    fireEvent.submit(screen.getByRole('button', { name: /Add to the bank|Adding/ }).closest('form')!)
    fireEvent.click(screen.getByRole('button', { name: 'Graphics' }))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/cappe/matcha-admin/studio-bank?kind=graphic'))
    await act(async () => finish(item()))
    expect(screen.queryByText('Harbour at dawn')).not.toBeInTheDocument()
    expect(await screen.findByText("Harbour at dawn is in every site's Studio")).toBeInTheDocument()
  })
})
