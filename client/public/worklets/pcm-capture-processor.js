/**
 * AudioWorklet processor that captures mic audio, resamples to 16 kHz mono,
 * buffers to ~4096-byte chunks, and converts Float32 -> Int16 PCM for Gemini Live API.
 *
 * Sends a message { type: 'flush' } from the main thread to flush remaining buffer.
 */
class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._targetRate = 16000
    this._buffer = new Int16Array(2048) // 4096 bytes (matches iOS chunk size)
    this._bufferOffset = 0

    this.port.onmessage = (e) => {
      if (e.data === 'flush' && this._bufferOffset > 0) {
        const chunk = this._buffer.slice(0, this._bufferOffset)
        this.port.postMessage(chunk.buffer, [chunk.buffer])
        this._buffer = new Int16Array(2048)
        this._bufferOffset = 0
      }
    }
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || !input[0] || input[0].length === 0) return true

    const src = input[0]
    const srcRate = sampleRate
    const ratio = srcRate / this._targetRate

    const outLen = Math.floor(src.length / ratio)
    if (outLen === 0) return true

    for (let i = 0; i < outLen; i++) {
      const srcIdx = i * ratio
      const lo = Math.floor(srcIdx)
      const hi = Math.min(lo + 1, src.length - 1)
      const frac = srcIdx - lo
      const sample = src[lo] + frac * (src[hi] - src[lo])
      this._buffer[this._bufferOffset++] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)))

      if (this._bufferOffset >= this._buffer.length) {
        const chunk = new Int16Array(this._buffer)
        this.port.postMessage(chunk.buffer, [chunk.buffer])
        this._buffer = new Int16Array(2048)
        this._bufferOffset = 0
      }
    }

    return true
  }
}

registerProcessor('pcm-capture-processor', PCMCaptureProcessor)
