// The Studio's server calls (server/app/cappe/routes/studio.py, blog.py).

import { cappeApi, cappeApiBase, cappeStreamHeaders } from '../api'
import type { CappeAsset } from '../types'
import type { Asset, Doc, Face } from './model/types'
import type { Recipe } from './picture/recipe'

export type StudioPost = {
  id: string; site_id: string; title: string; slug: string; excerpt: string | null; kicker: string | null
  byline: string | null; topic: string | null; access: 'free' | 'paid'; status: string
  published_at: string | null; updated_at: string; rev: number
}
export type Opened = { post: StudioPost; doc: Doc; draft: boolean; live: boolean }
/** One of the magazine's own fonts (server routes/studio_fonts.py): a face, and its upload. */
export type SiteFont = Face & { id: string; filename: string | null; hidden: boolean; created_at: string }
export type Saved = { rev: number; draft: boolean; doc: Doc }
export type Revision = { id: string; rev: number; kind: 'save' | 'publish' | 'restore' | 'convert'; title: string | null;
  created_at: string }
/** A button under an answer: a guide section to open, or a command to run. */
export type AskLink = { kind: 'guide' | 'command'; id: string }
export type AskAnswer = { answer: string; links: AskLink[] }
export type AskRequest = {
  question: string
  history: { q: string; a: string }[]
  guide: { id: string; title: string; body: string; points: string[] }[]
  commands: { id: string; label: string; keys: string; enabled: boolean }[]
  page: string
  picture: { media_type: 'image/jpeg'; data: string } | null
}

const base = (siteId: string, postId: string) => `/sites/${siteId}/studio/stories/${postId}`

const fontsPath = (siteId: string) => `/sites/${siteId}/studio/fonts`

export const studioApi = {
  /** The magazine's own fonts (not those taken off its list). */
  fonts: (siteId: string) => cappeApi.get<{ fonts: SiteFont[] }>(fontsPath(siteId)),
  /** A font file added to the magazine, under `name` (a family it already has joins it). */
  uploadFont: (siteId: string, file: File, opts: { name: string; licence: boolean; weight?: number; italic?: boolean }) => {
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('name', opts.name)
    form.append('licence_attested', opts.licence ? 'true' : 'false')
    if (opts.weight !== undefined) form.append('weight', String(opts.weight))
    if (opts.italic !== undefined) form.append('italic', opts.italic ? 'true' : 'false')
    return cappeApi.upload<SiteFont>(fontsPath(siteId), form)
  },
  renameFontFamily: (siteId: string, family: string, name: string) =>
    cappeApi.patch<{ family: string; name: string }>(`${fontsPath(siteId)}/families/${family}`, { name }),
  /** Off the magazine's list; pages that set it keep it. */
  hideFont: (siteId: string, fontId: string) => cappeApi.delete<void>(`${fontsPath(siteId)}/${fontId}`),
  open: (siteId: string, postId: string) => cappeApi.get<Opened>(base(siteId, postId)),
  save: (siteId: string, postId: string, body: { base_rev: number; doc: Doc; publish?: boolean; keep?: boolean }) =>
    cappeApi.put<Saved>(base(siteId, postId), { ...body, identity_version: 1 }),
  discard: (siteId: string, postId: string, baseRev: number) =>
    cappeApi.post<Saved>(`${base(siteId, postId)}/discard`, { base_rev: baseRev, identity_version: 1 }),
  revisions: (siteId: string, postId: string) => cappeApi.get<Revision[]>(`${base(siteId, postId)}/revisions`),
  restore: (siteId: string, postId: string, revisionId: string, baseRev: number) =>
    cappeApi.post<Saved>(`${base(siteId, postId)}/revisions/${revisionId}/restore`, { base_rev: baseRev, identity_version: 1 }),
  /** A new paged story, with its first two pages. */
  create: (siteId: string, title: string) =>
    cappeApi.post<{ id: string }>(`/sites/${siteId}/posts`, { title, format: 'pages' }),
  /** What isn't on the pages: title, status, topic, access… */
  updatePost: (siteId: string, postId: string, patch: Partial<StudioPost>) =>
    cappeApi.put<StudioPost>(`/sites/${siteId}/posts/${postId}`, patch),
  assets: (siteId: string) => cappeApi.get<{ assets: CappeAsset[] }>(`/sites/${siteId}/assets`),
  /** A library picture's own file, from our origin (the Picture Editor reads its pixels). */
  pixels: async (siteId: string, assetId: string): Promise<Blob> => {
    const res = await fetch(`${cappeApiBase}/sites/${siteId}/assets/${assetId}/pixels`, { headers: await cappeStreamHeaders() })
    if (!res.ok) throw new Error(res.status === 404 ? 'That picture isn’t in the library any more.' : `Couldn’t open the picture (${res.status}).`)
    return res.blob()
  },
  /** What the Picture Editor made of a picture, as a new library picture. */
  saveEdit: (siteId: string, assetId: string, file: Blob, recipe: Recipe) => {
    const form = new FormData()
    form.append('file', file, file.type === 'image/png' ? 'edited.png' : 'edited.jpg')
    form.append('recipe', JSON.stringify(recipe))
    return cappeApi.upload<CappeAsset>(`/sites/${siteId}/assets/${assetId}/edit`, form)
  },
  /** Ask the Studio: an answer, saved nowhere (server studio/ask.py). */
  ask: (siteId: string, postId: string, body: AskRequest) => cappeApi.post<AskAnswer>(`${base(siteId, postId)}/ask`, body),
  preview: (siteId: string, post: StudioPost, doc: Doc) => cappeApi.postHtml(`/sites/${siteId}/stories/preview`, {
    title: post.title, excerpt: post.excerpt, kicker: post.kicker, topic: post.topic, byline: post.byline,
    access: post.access, format: 'pages', content: { doc },
  }),
}

/** A library row as the page renderer needs it. */
export const toAsset = (a: CappeAsset): Asset => ({ id: a.id, url: a.url, alt: a.alt, credit_line: a.credit_line,
  license: a.license, ai_generated: a.ai_generated, source_url: a.source_url, width: a.width, height: a.height,
  variants: a.variants as Asset['variants'], kind: a.kind, parent: a.parent_asset_id ?? null,
  recipe: (a.recipe as Recipe | null) ?? null })
