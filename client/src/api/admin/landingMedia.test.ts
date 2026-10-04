import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import { api } from '../client'
import { landingMedia } from './landingMedia'
import { reportJsError } from '../errorReporter'
import type { CommercialUploadProgress } from '../../types/landingMedia'

vi.mock('../client', () => ({ API_BASE: '/api', api: { post: vi.fn() } }))
vi.mock('../errorReporter', () => ({ reportJsError: vi.fn() }))
const prepared = { upload_url: 'https://uploads.example.com', fields: { key: 'signed-key', 'Content-Type': 'video/mp4' }, asset_url: 'https://media.example.com/film.mp4' }
const file = () => new File(['video'], 'film.mp4', { type: 'video/mp4' })
const transport = () => ({
  open: vi.fn(), send: vi.fn(), setRequestHeader: vi.fn(), timeout: 0, status: 204, withCredentials: false,
  upload: { onprogress: null as ((event: ProgressEvent) => void) | null },
  onload: null as (() => void) | null, onerror: null as (() => void) | null,
  ontimeout: null as (() => void) | null, onabort: null as (() => void) | null,
})
let xhr: ReturnType<typeof transport>
beforeEach(() => {
  vi.clearAllMocks()
  xhr = transport()
  vi.stubGlobal('XMLHttpRequest', vi.fn(function () { return xhr }))
})
afterEach(() => vi.unstubAllGlobals())

describe('commercial upload transport', () => {
  it('reports prepare, real transfer progress, and verification before returning a URL', async () => {
    let verify!: (value: { url: string }) => void
    const verification = new Promise<{ url: string }>((resolve) => { verify = resolve })
    vi.mocked(api.post).mockResolvedValueOnce(prepared).mockReturnValueOnce(verification)
    const progress = vi.fn<(value: CommercialUploadProgress) => void>()
    const selected = file()
    const upload = landingMedia.uploadCommercial(selected, 'desktop_video', progress)
    await waitFor(() => expect(xhr.send).toHaveBeenCalledOnce())
    expect(progress.mock.calls.map(([value]) => value.phase)).toEqual(['preparing', 'uploading'])
    expect(xhr.open).toHaveBeenCalledWith('POST', prepared.upload_url)
    expect(xhr.setRequestHeader).not.toHaveBeenCalled()
    expect(xhr.withCredentials).toBe(false)
    const form = xhr.send.mock.calls[0][0] as FormData
    expect(form.get('key')).toBe('signed-key')
    expect(form.get('file')).toBe(selected)
    expect(xhr.timeout).toBe(15 * 60 * 1000)
    xhr.upload.onprogress?.(new ProgressEvent('progress', { lengthComputable: true, loaded: 50, total: 100 }))
    expect(progress).toHaveBeenLastCalledWith({ phase: 'uploading', percent: 50 })
    xhr.upload.onprogress?.(new ProgressEvent('progress', { lengthComputable: true, loaded: 100, total: 100 }))
    expect(vi.mocked(api.post)).toHaveBeenCalledTimes(1)
    xhr.onload?.()
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(progress).toHaveBeenLastCalledWith({ phase: 'verifying', percent: null })
    expect(api.post).toHaveBeenLastCalledWith('/admin/landing-media/scheduling-commercial/complete', { filename: 'film.mp4', content_type: 'video/mp4', size: selected.size, slot: 'desktop_video', asset_url: prepared.asset_url })
    verify({ url: prepared.asset_url })
    await expect(upload).resolves.toBe(prepared.asset_url)
  })
  it('does not invent progress for an unmeasurable transfer', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(prepared).mockResolvedValueOnce({ url: prepared.asset_url })
    const progress = vi.fn()
    const upload = landingMedia.uploadCommercial(file(), 'desktop_video', progress)
    await waitFor(() => expect(xhr.send).toHaveBeenCalledOnce())
    xhr.upload.onprogress?.(new ProgressEvent('progress', { loaded: 10 }))
    expect(progress).toHaveBeenLastCalledWith({ phase: 'uploading', percent: null })
    xhr.onload?.()
    await upload
  })
  it('never verifies a rejected S3 upload', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(prepared)
    const upload = landingMedia.uploadCommercial(file(), 'desktop_video', vi.fn())
    const rejected = expect(upload).rejects.toThrow('S3 rejected')
    await waitFor(() => expect(xhr.send).toHaveBeenCalledOnce())
    xhr.status = 403
    xhr.onload?.()
    await rejected
    expect(api.post).toHaveBeenCalledTimes(1)
  })
  it.each([
    ['onerror', 'could not reach S3'], ['ontimeout', 'timed out'], ['onabort', 'interrupted'],
  ] as const)('settles %s without completing or publishing an upload', async (event, message) => {
    vi.mocked(api.post).mockResolvedValueOnce(prepared)
    const upload = landingMedia.uploadCommercial(file(), 'desktop_video', vi.fn())
    const rejected = expect(upload).rejects.toThrow(message)
    await waitFor(() => expect(xhr.send).toHaveBeenCalledOnce())
    xhr[event]?.()
    await rejected
    expect(api.post).toHaveBeenCalledTimes(1)
  })
  it('reports S3 transfer failures with CORS-diagnosing context, but not user aborts', async () => {
    xhr.status = 0
    vi.mocked(api.post).mockResolvedValue(prepared)
    const run = async (event: 'onerror' | 'onload' | 'ontimeout' | 'onabort') => {
      vi.mocked(reportJsError).mockClear()
      const upload = landingMedia.uploadCommercial(file(), 'desktop_video', vi.fn())
      const settled = upload.catch(() => undefined)
      await waitFor(() => expect(xhr.send).toHaveBeenCalled())
      xhr[event]?.()
      await settled
    }
    await run('onerror')
    expect(reportJsError).toHaveBeenCalledOnce()
    const [error, context] = vi.mocked(reportJsError).mock.calls[0]
    expect((error as Error).message).toContain('could not reach S3')
    expect(context).toEqual({
      source: 'landing-media-s3-upload', outcome: 'unreachable', slot: 'desktop_video', size: 5,
      content_type: 'video/mp4', http_status: 0, upload_host: 'uploads.example.com', page_origin: window.location.origin,
    })
    xhr.status = 403
    await run('onload')
    expect(vi.mocked(reportJsError).mock.calls[0][1]).toMatchObject({ outcome: 'rejected', http_status: 403 })
    await run('ontimeout')
    expect(vi.mocked(reportJsError).mock.calls[0][1]).toMatchObject({ outcome: 'timeout' })
    await run('onabort')
    expect(reportJsError).not.toHaveBeenCalled()
  })
  it('does not send a file when preparing the upload fails', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('Not configured'))
    const progress = vi.fn()
    await expect(landingMedia.uploadCommercial(file(), 'desktop_video', progress)).rejects.toThrow('Not configured')
    expect(xhr.send).not.toHaveBeenCalled()
    expect(progress).toHaveBeenCalledOnce()
  })
  it('does not return a URL when verification fails after transfer', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(prepared).mockRejectedValueOnce(new Error('The upload is missing or incomplete'))
    const upload = landingMedia.uploadCommercial(file(), 'desktop_video', vi.fn())
    const rejected = expect(upload).rejects.toThrow('missing or incomplete')
    await waitFor(() => expect(xhr.send).toHaveBeenCalledOnce())
    xhr.onload?.()
    await rejected
  })
})
