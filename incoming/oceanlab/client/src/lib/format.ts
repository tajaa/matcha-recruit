export function displayIsrc(isrc: string | null | undefined): string {
  if (!isrc || isrc.length !== 12) return isrc ?? ''
  return `${isrc.slice(0, 2)}-${isrc.slice(2, 5)}-${isrc.slice(5, 7)}-${isrc.slice(7, 12)}`
}
