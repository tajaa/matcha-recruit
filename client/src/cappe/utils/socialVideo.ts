// Dropping a video into the Social composer: the file goes straight to
// storage (it is usually bigger than the API takes), then the server checks it
// and cuts it to size for each network. These helpers are the browser's half.
import { cappeApi } from '../api'
import type { CappeSocialAsset, CappeSocialAssetUpload } from '../types'

export const VIDEO_TYPES = ['video/mp4', 'video/quicktime', 'video/webm']
export const MAX_VIDEO_MB = 500

/** Why this file can't be dropped as a video, or null. */
export function videoProblem(file: File): string | null {
  if (!VIDEO_TYPES.includes(file.type)) return 'Videos must be MP4, MOV or WebM'
  if (file.size > MAX_VIDEO_MB * 1024 * 1024) return `Videos can be up to ${MAX_VIDEO_MB} MB`
  if (!file.size) return 'That file is empty'
  return null
}

/** The frame the queue and the composer show for a video. */
export function posterOf(asset: Pick<CappeSocialAsset, 'frames'>): string | null {
  const frames = asset.frames ?? []
  return frames.length ? frames[Math.floor(frames.length / 2)].url : null
}

function sendToStorage(prepared: CappeSocialAssetUpload, file: File, onProgress: (percent: number | null) => void) {
  const form = new FormData()
  for (const [key, value] of Object.entries(prepared.fields)) form.append(key, value)
  form.append('file', file)
  // This signed POST goes straight to storage; never attach the app's auth headers.
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', prepared.upload_url)
    xhr.timeout = 15 * 60 * 1000
    xhr.upload.onprogress = (event) => {
      onProgress(event.lengthComputable && event.total > 0 ? Math.min(100, Math.round((event.loaded / event.total) * 100)) : null)
    }
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('Storage refused the upload. Try again.')))
    xhr.onerror = () => reject(new Error('The upload couldn’t reach storage. Check your connection and try again.'))
    xhr.ontimeout = () => reject(new Error('The upload timed out. Try a shorter clip.'))
    xhr.onabort = () => reject(new Error('Upload stopped.'))
    xhr.send(form)
  })
}

/** Upload one video and hand it to the server; resolves with the asset
 *  (usually `rendering`). */
export async function uploadVideo(siteId: string, file: File, onProgress: (percent: number | null) => void) {
  const base = `/sites/${siteId}/social/assets`
  const prepared = await cappeApi.post<CappeSocialAssetUpload>(`${base}/presign`, {
    filename: file.name, content_type: file.type, size: file.size,
  })
  await sendToStorage(prepared, file, onProgress)
  return cappeApi.post<CappeSocialAsset>(`${base}/${prepared.asset_id}/complete`)
}
