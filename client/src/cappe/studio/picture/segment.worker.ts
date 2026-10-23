/// <reference lib="webworker" />
// The cut-out model, off the page's thread: SlimSAM (Apache-2.0) on
// onnxruntime's WebAssembly backend, one thread (the dashboard isn't
// cross-origin isolated). The page sends the model's bytes, then the picture
// once (encoded: about three seconds), then clicks; each click answers with a
// mask the picture's own size (samMath.ts).

import * as ort from 'onnxruntime-web/wasm'
import wasmUrl from 'onnxruntime-web/ort-wasm-simd-threaded.wasm?url'
import { MASK_SIZE, SAM_SIZE, bestMask, maskAlpha, pixelTensor, promptOf, samSize } from './samMath'

export type ToWorker =
  | { type: 'load'; encoder: ArrayBuffer; decoder: ArrayBuffer }
  | { type: 'encode'; image: ImageBitmap; width: number; height: number }
  | { type: 'mask'; id: number; points: { x: number; y: number; keep: boolean }[] }
export type FromWorker =
  | { type: 'loaded' }
  | { type: 'encoded'; ms: number }
  | { type: 'mask'; id: number; alpha: Uint8Array; width: number; height: number; score: number }
  | { type: 'error'; id?: number; message: string }

ort.env.wasm.wasmPaths = { wasm: wasmUrl }
ort.env.wasm.numThreads = 1

let encoder: ort.InferenceSession | null = null
let decoder: ort.InferenceSession | null = null
let embedded: Record<string, ort.Tensor> | null = null
let size = { width: 0, height: 0 }

const post = (m: FromWorker, transfer: Transferable[] = []) => (self as DedicatedWorkerGlobalScope).postMessage(m, transfer)

async function encode(image: ImageBitmap, width: number, height: number): Promise<void> {
  const { w, h } = samSize(width, height)
  const canvas = new OffscreenCanvas(w, h)
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(image, 0, 0, w, h)
  image.close()
  const input = new ort.Tensor('float32', pixelTensor(ctx.getImageData(0, 0, w, h).data, w, h), [1, 3, SAM_SIZE, SAM_SIZE])
  const out = await encoder!.run({ [encoder!.inputNames[0]]: input })
  embedded = out as Record<string, ort.Tensor>
  size = { width, height }
}

async function mask(id: number, points: { x: number; y: number; keep: boolean }[]): Promise<void> {
  const { coords, labels } = promptOf(points, size.width, size.height)
  const feeds: Record<string, ort.Tensor> = {
    input_points: new ort.Tensor('float32', coords, [1, 1, points.length, 2]),
    input_labels: new ort.Tensor('int64', BigInt64Array.from(labels), [1, 1, points.length]),
  }
  for (const name of decoder!.inputNames) if (embedded![name]) feeds[name] = embedded![name]
  const out = await decoder!.run(feeds)
  const scores = out.iou_scores.data as Float32Array
  const best = bestMask(scores)
  const cell = MASK_SIZE * MASK_SIZE
  const logits = (out.pred_masks.data as Float32Array).subarray(best * cell, (best + 1) * cell)
  const alpha = maskAlpha(logits, size.width, size.height)
  post({ type: 'mask', id, alpha, width: size.width, height: size.height, score: scores[best] }, [alpha.buffer])
}

self.onmessage = async (e: MessageEvent<ToWorker>) => {
  const m = e.data
  try {
    if (m.type === 'load') {
      const opts: ort.InferenceSession.SessionOptions = { executionProviders: ['wasm'] }
      encoder = await ort.InferenceSession.create(new Uint8Array(m.encoder), opts)
      decoder = await ort.InferenceSession.create(new Uint8Array(m.decoder), opts)
      post({ type: 'loaded' })
    } else if (m.type === 'encode') {
      const t0 = performance.now()
      await encode(m.image, m.width, m.height)
      post({ type: 'encoded', ms: Math.round(performance.now() - t0) })
    } else if (m.type === 'mask') {
      await mask(m.id, m.points)
    }
  } catch (err) {
    post({ type: 'error', id: m.type === 'mask' ? m.id : undefined, message: err instanceof Error ? err.message : String(err) })
  }
}
