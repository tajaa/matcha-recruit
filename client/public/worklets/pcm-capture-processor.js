/**
 * AudioWorklet processor that captures mic audio, resamples to 16 kHz mono,
 * and converts Float32 -> Int16 PCM for Gemini Live API.
 */
class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._targetRate = 16000
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || !input[0] || input[0].length === 0) return true

    const src = input[0] // Float32Array, mono channel 0
    const srcRate = sampleRate // global in AudioWorklet scope
    const ratio = srcRate / this._targetRate

    // Resample via linear interpolation
    const outLen = Math.floor(src.length / ratio)
    if (outLen === 0) return true

    const pcm16 = new Int16Array(outLen)
    for (let i = 0; i < outLen; i++) {
      const srcIdx = i * ratio
      const lo = Math.floor(srcIdx)
      const hi = Math.min(lo + 1, src.length - 1)
      const frac = srcIdx - lo
      const sample = src[lo] + frac * (src[hi] - src[lo])
      // Clamp and convert to Int16
      pcm16[i] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)))
    }

    this.port.postMessage(pcm16.buffer, [pcm16.buffer])
    return true
  }
}

registerProcessor('pcm-capture-processor', PCMCaptureProcessor)
