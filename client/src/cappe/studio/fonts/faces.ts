// The Studio's own faces (server studio/fonts.py, fonts_manifest.json): every
// catalog face built as a static file named by its sha256, served from our
// origin. The Studio measures those bytes (compose/shaper.ts) and shows them
// under a name of their own (`f-<sha>`), the name a reader's page uses too.

import { registerFaces } from '../model/doc'
import { CHAR_DEFAULTS } from '../model/limits'
import type { Face } from '../model/types'

export type Manifest = { version: string; faces: Face[] }
export type FaceLookup = (family: string, weight: number, italic: boolean) => Face | undefined

export const familyName = (sha: string) => `f-${sha.slice(0, 16)}`
export const faceUrl = (sha: string) => `/api/cappe/public/fonts/${sha}.ttf`

export class FaceBook {
  private byStyle = new Map<string, Face>()
  private bySha = new Map<string, Face>()
  readonly manifest: Manifest

  constructor(manifest: Manifest) {
    this.manifest = manifest
    this.add(manifest.faces)
  }

  /** Faces besides the manifest's: the magazine's own fonts (a story carries
   *  those it names, `doc.faces`; the Studio lists the site's). */
  add(faces: Iterable<Face>): void {
    const list = [...faces]
    for (const f of list) {
      this.byStyle.set(`${f.family}|${f.weight}|${f.italic ? 1 : 0}`, f)
      this.bySha.set(f.sha, f)
    }
    registerFaces(list)
  }

  face: FaceLookup = (family, weight, italic) => this.byStyle.get(`${family}|${weight}|${italic ? 1 : 0}`)

  sha(sha: string): Face | undefined {
    return this.bySha.get(sha)
  }

  /** The face to measure with: the run's, else the default (never nothing,
   *  so a face missing from a build still sets type). */
  measureFace(family: string, weight: number, italic: boolean): Face | undefined {
    return this.face(family, weight, italic) ?? this.face(CHAR_DEFAULTS.font, CHAR_DEFAULTS.wt, false)
      ?? this.manifest.faces[0]
  }
}

let loading: Promise<Manifest> | null = null

export function loadManifest(fetcher: typeof fetch = fetch): Promise<Manifest> {
  loading ??= fetcher('/api/cappe/public/fonts/manifest.json').then(async (res) => {
    if (!res.ok) throw new Error('The Studio’s fonts couldn’t be loaded.')
    return (await res.json()) as Manifest
  }).catch((err) => {
    loading = null
    throw err
  })
  return loading
}
