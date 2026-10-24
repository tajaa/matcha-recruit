import type { CappeAsset, CappeStockImport, CappeStockSearchSource } from '../../types'

/** The smallest stored size that still fills a thumbnail, else the original. */
export function thumbUrl(asset: CappeAsset): string {
  return asset.variants?.webp?.[0]?.url || asset.url
}

/** An upload's credit is the owner's to write; an archive picture's comes from
 *  its license and an AI picture is always credited as AI (the server 422s). */
export function creditEditable(asset: CappeAsset): boolean {
  return asset.kind === 'upload' && !asset.ai_generated
}

export const STOCK_SOURCES: { key: CappeStockSearchSource; label: string; hint: string }[] = [
  { key: 'stock', label: 'Free photos', hint: 'Modern photos free for any use (CC0), from StockSnap.io, WordPress and Nappy' },
  { key: 'openverse', label: 'Openverse', hint: 'Creative Commons photos from Flickr, Wikimedia and more' },
  { key: 'smithsonian', label: 'Smithsonian', hint: 'Public-domain collections of the Smithsonian museums' },
  { key: 'met', label: 'The Met', hint: 'Public-domain art from The Metropolitan Museum of Art' },
  { key: 'nasa', label: 'NASA', hint: 'Space, Earth and science pictures from NASA' },
]

/** "CC BY 2.0", "CC0", "Public domain" — the badge on an archive picture. */
export function licenseLabel(license: string | null, version?: string | null): string {
  switch (license) {
    case 'cc0': return 'CC0'
    case 'pdm': return 'Public domain'
    case 'by': return `CC BY${version ? ` ${version}` : ''}`
    case 'by-sa': return `CC BY-SA${version ? ` ${version}` : ''}`
    default: return license || ''
  }
}

export const stockKey = (item: { source: string; source_id: string }) => `${item.source}:${item.source_id}`

export function importOpen(job: CappeStockImport): boolean {
  return job.status === 'pending' || job.status === 'working'
}
