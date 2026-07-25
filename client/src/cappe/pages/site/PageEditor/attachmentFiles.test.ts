// The paste/drop path hands Merlin whatever the OS produced. These are the pure
// selection bits — the canvas re-encode in prepareImageFile needs a real
// browser, so it isn't covered here.
// Run:  npm run test:run -- attachmentFiles
import { describe, expect, it } from 'vitest'
import { imageFilesFrom, imageFilesFromClipboard, isImageFile } from './attachmentFiles'

const file = (name: string, type: string) => new File([new Uint8Array([1, 2, 3])], name, { type })

/** Minimal stand-in for the parts of DataTransfer we read — jsdom's own
 *  DataTransfer can't be populated with files. */
const clipboard = (files: File[], items: { kind: string; file: File | null }[]) =>
  ({
    files,
    items: items.map((i) => ({ kind: i.kind, getAsFile: () => i.file })),
  } as unknown as DataTransfer)

describe('isImageFile', () => {
  it('accepts declared image types', () => {
    expect(isImageFile(file('shot.png', 'image/png'))).toBe(true)
    expect(isImageFile(file('photo.heic', 'image/heic'))).toBe(true)
  })

  it('falls back to the extension when the OS gave no type', () => {
    expect(isImageFile(file('Screenshot 2026-07-25.PNG', ''))).toBe(true)
    expect(isImageFile(file('notes', ''))).toBe(false)
  })

  it('rejects non-images', () => {
    expect(isImageFile(file('contract.pdf', 'application/pdf'))).toBe(false)
  })
})

describe('imageFilesFrom', () => {
  it('keeps only images, in order', () => {
    const files = [file('a.png', 'image/png'), file('b.pdf', 'application/pdf'), file('c.jpg', 'image/jpeg')]
    expect(imageFilesFrom(files).map((f) => f.name)).toEqual(['a.png', 'c.jpg'])
  })

  it('tolerates an empty drop', () => {
    expect(imageFilesFrom(null)).toEqual([])
  })
})

describe('imageFilesFromClipboard', () => {
  it('reads the item list when files is empty (screenshot paste)', () => {
    const shot = file('image.png', 'image/png')
    expect(imageFilesFromClipboard(clipboard([], [{ kind: 'file', file: shot }]))).toHaveLength(1)
  })

  it('does not double-count a bitmap present in both files and items', () => {
    const shot = file('image.png', 'image/png')
    expect(imageFilesFromClipboard(clipboard([shot], [{ kind: 'file', file: shot }]))).toHaveLength(1)
  })

  it('does not double-count when each accessor mints its own File object', () => {
    // Chrome's real behavior: clipboardData.files[0] and items[i].getAsFile()
    // are DISTINCT File objects for one bitmap, created a moment apart — so
    // lastModified differs and only name+size identifies them as the same shot.
    const fromFiles = new File([new Uint8Array([1, 2, 3])], 'image.png', {
      type: 'image/png', lastModified: 1000,
    })
    const fromItems = new File([new Uint8Array([1, 2, 3])], 'image.png', {
      type: 'image/png', lastModified: 1007,
    })
    expect(imageFilesFromClipboard(clipboard([fromFiles], [{ kind: 'file', file: fromItems }]))).toHaveLength(1)
  })

  it('ignores pasted text', () => {
    expect(imageFilesFromClipboard(clipboard([], [{ kind: 'string', file: null }]))).toEqual([])
  })
})
