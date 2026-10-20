import type { CappeAsset } from '../../types'

/** The smallest stored size that still fills a thumbnail, else the original. */
export function thumbUrl(asset: CappeAsset): string {
  return asset.variants?.webp?.[0]?.url || asset.url
}

/** An upload's credit is the owner's to write; an archive picture's comes from
 *  its license and an AI picture is always credited as AI (the server 422s). */
export function creditEditable(asset: CappeAsset): boolean {
  return asset.kind === 'upload' && !asset.ai_generated
}
