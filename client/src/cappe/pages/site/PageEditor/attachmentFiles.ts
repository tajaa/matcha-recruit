/** Turning whatever the OS hands the panel into something the upload route takes.
 *
 *  A screenshot reaches Merlin three ways now — the file picker, a paste (macOS
 *  ⌘⇧⌃4 lands the shot on the clipboard, never on disk), and a drop. The last
 *  two hand us files nobody sanitized: a Retina full-screen PNG is routinely
 *  8–15 MB, and `POST /sites/{id}/upload` refuses anything over 5 MB with a
 *  bare 413. So the "just drag it in" path has to shrink first, or it fails on
 *  exactly the screenshots people take.
 *
 *  Re-encoding is a fallback, not the default: a file that already fits the
 *  route's allowlist and size cap is passed through untouched (uploads land in
 *  the asset library and can be placed on a real page, so we don't want to
 *  silently JPEG a clean PNG). The server does its own downscale to 1280px for
 *  the model — MAX_EDGE here is about what gets STORED.
 */

/** Mirrors `_ALLOWED` in server/app/cappe/routes/uploads.py. No SVG (stored XSS). */
export const ALLOWED_IMAGE_MIMES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
/** Mirrors `_MAX_BYTES` in the same route. */
export const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
/** Mirrors merlin_attachments.MAX_ATTACHMENTS — the per-turn context budget. */
export const MAX_ATTACHMENTS = 4

const MAX_EDGE = 2560
const QUALITY_STEPS = [0.85, 0.7, 0.55]

/** True for anything we'd try to attach. Deliberately looser than the route's
 *  allowlist — a HEIC/TIFF paste is worth *trying* to transcode rather than
 *  rejecting on sight; `prepareImageFile` is where it fails if the browser
 *  can't decode it. Some drops (and Windows clipboard images) arrive with an
 *  empty `type`, hence the extension fallback. */
export function isImageFile(file: File): boolean {
  if (file.type) return file.type.startsWith('image/')
  return /\.(png|jpe?g|gif|webp|bmp|heic|heif|tiff?)$/i.test(file.name || '')
}

/** Image files out of a drop or a paste, in the order they arrived. */
export function imageFilesFrom(files: ArrayLike<File> | null | undefined): File[] {
  return Array.from(files ?? []).filter(isImageFile)
}

/** Images on a clipboard payload. `clipboardData.files` is empty for a
 *  screenshot paste in some browsers, so read the item list too and dedupe on
 *  identity — Chrome populates both for the same bitmap. */
export function imageFilesFromClipboard(data: DataTransfer | null): File[] {
  if (!data) return []
  const out: File[] = imageFilesFrom(data.files)
  for (const item of Array.from(data.items ?? [])) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    if (!file || !isImageFile(file)) continue
    if (!out.some((f) => f.name === file.name && f.size === file.size && f.lastModified === file.lastModified)) {
      out.push(file)
    }
  }
  return out
}

function loadBitmap(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === 'function') return createImageBitmap(file)
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new window.Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode failed')) }
    img.src = url
  })
}

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
}

/** A file the upload route will accept, or `null` if the browser couldn't
 *  decode it (HEIC on a browser without support, a corrupt paste).
 *
 *  Never throws: the caller reports one message per rejected file rather than
 *  failing the whole drop. */
export async function prepareImageFile(file: File): Promise<File | null> {
  const alreadyFine = ALLOWED_IMAGE_MIMES.includes(file.type) && file.size <= MAX_ATTACHMENT_BYTES
  if (alreadyFine) return file

  let source: ImageBitmap | HTMLImageElement
  try {
    source = await loadBitmap(file)
  } catch {
    return null
  }
  try {
    const w = 'width' in source ? source.width : 0
    const h = 'height' in source ? source.height : 0
    if (!w || !h) return null
    const scale = Math.min(1, MAX_EDGE / Math.max(w, h))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(w * scale))
    canvas.height = Math.max(1, Math.round(h * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    // JPEG has no alpha — without this a transparent PNG's background composites
    // to black instead of the white the screenshot appeared to have.
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(source as CanvasImageSource, 0, 0, canvas.width, canvas.height)

    for (const quality of QUALITY_STEPS) {
      const blob = await toBlob(canvas, quality)
      if (!blob) return null
      if (blob.size <= MAX_ATTACHMENT_BYTES) {
        const name = (file.name || 'screenshot').replace(/\.[^.]+$/, '') + '.jpg'
        return new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() })
      }
    }
    return null
  } catch {
    return null
  } finally {
    if ('close' in source && typeof source.close === 'function') source.close()
  }
}
