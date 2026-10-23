// The page's side of the cut-out model (segment.worker.ts): fetch the model
// (about 14 MB, once a session; the browser keeps it a year by its sha),
// start the worker, encode the picture, and turn clicks into masks.

import { cappeApiBase, cappeApi, cappeStreamHeaders } from '../../api'
import type { CutPoint } from './recipe'
import type { FromWorker, ToWorker } from './segment.worker'

export type Mask = { alpha: Uint8Array; width: number; height: number; score: number }
type ModelFile = { path: string; sha: string; bytes: number }
type Manifest = { models: { segment: { files: { encoder: ModelFile; decoder: ModelFile }; licence: string; source: string } } }

/** What the Picture Editor needs of the model (a fake stands in for it in tests). */
export interface Segmenter {
  load(onProgress: (done: number, total: number) => void): Promise<void>
  encode(image: ImageBitmap, width: number, height: number): Promise<void>
  mask(points: CutPoint[]): Promise<Mask>
  dispose(): void
}

async function fetchModel(file: ModelFile, onBytes: (n: number) => void): Promise<ArrayBuffer> {
  const res = await fetch(`${cappeApiBase}/studio/models/${file.sha}.onnx`, { headers: await cappeStreamHeaders() })
  if (!res.ok || !res.body) throw new Error(res.status === 404 ? 'The cut-out model isn’t on this server yet.' : `Couldn’t fetch the cut-out model (${res.status}).`)
  const out = new Uint8Array(file.bytes)
  const reader = res.body.getReader()
  let at = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (at + value.length > out.length) throw new Error('The cut-out model isn’t the size it should be.')
    out.set(value, at)
    at += value.length
    onBytes(value.length)
  }
  if (at !== out.length) throw new Error('The cut-out model arrived incomplete.')
  return out.buffer
}

export class WorkerSegmenter implements Segmenter {
  private worker: Worker
  private next = 1
  private waiting = new Map<number | string, { resolve: (m: FromWorker) => void; reject: (e: Error) => void }>()

  constructor() {
    this.worker = new Worker(new URL('./segment.worker.ts', import.meta.url), { type: 'module' })
    this.worker.onmessage = (e: MessageEvent<FromWorker>) => {
      const m = e.data
      const key = m.type === 'mask' || (m.type === 'error' && m.id !== undefined) ? (m as { id: number }).id : 'step'
      const w = this.waiting.get(key)
      if (!w) return
      this.waiting.delete(key)
      if (m.type === 'error') w.reject(new Error(m.message))
      else w.resolve(m)
    }
    this.worker.onerror = (e) => {
      for (const w of this.waiting.values()) w.reject(new Error(e.message || 'The cut-out stopped.'))
      this.waiting.clear()
    }
  }

  private ask(m: ToWorker, transfer: Transferable[] = [], key: number | string = 'step'): Promise<FromWorker> {
    return new Promise((resolve, reject) => {
      this.waiting.set(key, { resolve, reject })
      this.worker.postMessage(m, transfer)
    })
  }

  async load(onProgress: (done: number, total: number) => void): Promise<void> {
    const { models } = await cappeApi.get<Manifest>('/studio/models/manifest.json')
    const { encoder, decoder } = models.segment.files
    const total = encoder.bytes + decoder.bytes
    let done = 0
    const tick = (n: number) => { done += n; onProgress(done, total) }
    const [enc, dec] = await Promise.all([fetchModel(encoder, tick), fetchModel(decoder, tick)])
    await this.ask({ type: 'load', encoder: enc, decoder: dec }, [enc, dec])
  }

  async encode(image: ImageBitmap, width: number, height: number): Promise<void> {
    await this.ask({ type: 'encode', image, width, height }, [image])
  }

  async mask(points: CutPoint[]): Promise<Mask> {
    const id = this.next++
    const m = await this.ask({ type: 'mask', id, points }, [], id)
    if (m.type !== 'mask') throw new Error('The cut-out answered something else.')
    return { alpha: m.alpha, width: m.width, height: m.height, score: m.score }
  }

  dispose(): void {
    this.worker.terminate()
    this.waiting.clear()
  }
}
