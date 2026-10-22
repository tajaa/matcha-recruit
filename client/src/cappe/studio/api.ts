// The Studio's server calls (server/app/cappe/routes/studio.py, blog.py).

import { cappeApi } from '../api'
import type { CappeAsset } from '../types'
import type { Asset, Doc } from './model/types'

export type StudioPost = {
  id: string; site_id: string; title: string; slug: string; excerpt: string | null; kicker: string | null
  byline: string | null; topic: string | null; access: 'free' | 'paid'; status: string
  published_at: string | null; updated_at: string; rev: number
}
export type Opened = { post: StudioPost; doc: Doc; draft: boolean; live: boolean }
export type Saved = { rev: number; draft: boolean; doc: Doc }
export type Revision = { id: string; rev: number; kind: 'save' | 'publish' | 'restore' | 'convert'; title: string | null;
  created_at: string }

const base = (siteId: string, postId: string) => `/sites/${siteId}/studio/stories/${postId}`

export const studioApi = {
  open: (siteId: string, postId: string) => cappeApi.get<Opened>(base(siteId, postId)),
  save: (siteId: string, postId: string, body: { base_rev: number; doc: Doc; publish?: boolean; keep?: boolean }) =>
    cappeApi.put<Saved>(base(siteId, postId), body),
  discard: (siteId: string, postId: string, baseRev: number) =>
    cappeApi.post<Saved>(`${base(siteId, postId)}/discard`, { base_rev: baseRev }),
  revisions: (siteId: string, postId: string) => cappeApi.get<Revision[]>(`${base(siteId, postId)}/revisions`),
  restore: (siteId: string, postId: string, revisionId: string, baseRev: number) =>
    cappeApi.post<Saved>(`${base(siteId, postId)}/revisions/${revisionId}/restore`, { base_rev: baseRev }),
  /** A new paged story, with its first two pages. */
  create: (siteId: string, title: string) =>
    cappeApi.post<{ id: string }>(`/sites/${siteId}/posts`, { title, format: 'pages' }),
  /** What isn't on the pages: title, status, topic, access… */
  updatePost: (siteId: string, postId: string, patch: Partial<StudioPost>) =>
    cappeApi.put<StudioPost>(`/sites/${siteId}/posts/${postId}`, patch),
  assets: (siteId: string) => cappeApi.get<{ assets: CappeAsset[] }>(`/sites/${siteId}/assets`),
  preview: (siteId: string, post: StudioPost, doc: Doc) => cappeApi.postHtml(`/sites/${siteId}/stories/preview`, {
    title: post.title, excerpt: post.excerpt, kicker: post.kicker, topic: post.topic, byline: post.byline,
    access: post.access, format: 'pages', content: { doc },
  }),
}

/** A library row as the page renderer needs it. */
export const toAsset = (a: CappeAsset): Asset => ({ id: a.id, url: a.url, alt: a.alt, credit_line: a.credit_line,
  license: a.license, ai_generated: a.ai_generated, source_url: a.source_url, width: a.width, height: a.height,
  variants: a.variants as Asset['variants'] })
