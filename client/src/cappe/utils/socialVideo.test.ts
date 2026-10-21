import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

import { MAX_VIDEO_MB, posterOf, uploadVideo, videoProblem } from './socialVideo'

const file = (type: string, size: number) => new File([new Uint8Array(Math.min(size, 16))], 'clip', { type })
const sized = (type: string, size: number) => Object.defineProperty(file(type, 1), 'size', { value: size })

class FakeXhr {
  static status = 204
  static sent: FormData[] = []
  status = 0
  timeout = 0
  upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
  onload?: () => void
  onerror?: () => void
  ontimeout?: () => void
  onabort?: () => void
  open = vi.fn()
  send(form: FormData) {
    FakeXhr.sent.push(form)
    this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 })
    this.status = FakeXhr.status
    if (this.status === 0) this.onerror?.()
    else this.onload?.()
  }
}

beforeEach(() => {
  api.post.mockReset()
  FakeXhr.status = 204
  FakeXhr.sent = []
  vi.stubGlobal('XMLHttpRequest', FakeXhr)
})
afterEach(() => vi.unstubAllGlobals())

describe('socialVideo', () => {
  it('takes MP4, MOV and WebM up to the size limit', () => {
    expect(videoProblem(file('video/mp4', 10))).toBeNull()
    expect(videoProblem(file('video/quicktime', 10))).toBeNull()
    expect(videoProblem(file('video/x-msvideo', 10))).toBe('Videos must be MP4, MOV or WebM')
    expect(videoProblem(sized('video/mp4', MAX_VIDEO_MB * 1024 * 1024 + 1))).toBe(`Videos can be up to ${MAX_VIDEO_MB} MB`)
    expect(videoProblem(sized('video/webm', 0))).toBe('That file is empty')
  })

  it('shows the middle frame as the poster', () => {
    expect(posterOf({ frames: [] })).toBeNull()
    expect(posterOf({ frames: [{ url: 'a', t_ms: 1 }, { url: 'b', t_ms: 2 }, { url: 'c', t_ms: 3 }] })).toBe('b')
  })

  it('posts the file straight to storage, then completes it', async () => {
    api.post.mockImplementation((path: string) => path.endsWith('/presign')
      ? Promise.resolve({ asset_id: 'a-1', upload_url: 'https://bucket.example.test/', fields: { key: 'k1' }, max_bytes: 1 })
      : Promise.resolve({ id: 'a-1', status: 'rendering' }))
    const progress = vi.fn()
    const clip = file('video/mp4', 10)
    const asset = await uploadVideo('s-1', clip, progress)
    expect(asset).toEqual({ id: 'a-1', status: 'rendering' })
    expect(api.post.mock.calls[0]).toEqual(['/sites/s-1/social/assets/presign',
      { filename: 'clip', content_type: 'video/mp4', size: clip.size }])
    expect(api.post.mock.calls[1][0]).toBe('/sites/s-1/social/assets/a-1/complete')
    expect(progress).toHaveBeenCalledWith(50)
    // The signed fields come first; the file is last.
    expect([...FakeXhr.sent[0].keys()]).toEqual(['key', 'file'])
  })

  it('reports a refused or unreachable upload and never completes it', async () => {
    api.post.mockResolvedValue({ asset_id: 'a-1', upload_url: 'https://bucket.example.test/', fields: {}, max_bytes: 1 })
    FakeXhr.status = 403
    await expect(uploadVideo('s-1', file('video/mp4', 10), vi.fn())).rejects.toThrow('Storage refused the upload')
    FakeXhr.status = 0
    await expect(uploadVideo('s-1', file('video/mp4', 10), vi.fn())).rejects.toThrow('couldn’t reach storage')
    expect(api.post).toHaveBeenCalledTimes(2)
  })
})
