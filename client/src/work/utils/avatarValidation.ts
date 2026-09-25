const MAX_AVATAR_BYTES = 5 * 1024 * 1024
const AVATAR_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

export function avatarValidationError(file: File): string | null {
  if (!AVATAR_TYPES.has(file.type)) return 'Choose a JPEG, PNG, or WebP image.'
  if (file.size > MAX_AVATAR_BYTES) return 'Choose an image under 5 MB.'
  return null
}
