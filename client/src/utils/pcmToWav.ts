// Assemble 16 kHz mono Int16 PCM frames (from the pcm-capture-processor worklet)
// into a single WAV blob. Gemini's audio understanding accepts WAV; it does NOT
// accept the webm/opus that MediaRecorder produces — hence this manual path.

export function pcmFramesToWavBlob(frames: ArrayBuffer[], sampleRate = 16000): Blob {
  let dataLen = 0
  for (const f of frames) dataLen += f.byteLength

  const channels = 1
  const bitsPerSample = 16
  const byteRate = (sampleRate * channels * bitsPerSample) / 8
  const blockAlign = (channels * bitsPerSample) / 8

  const buffer = new ArrayBuffer(44 + dataLen)
  const view = new DataView(buffer)
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i))
  }

  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + dataLen, true) // chunk size
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true) // subchunk1 size (PCM)
  view.setUint16(20, 1, true) // audio format = PCM
  view.setUint16(22, channels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bitsPerSample, true)
  writeStr(36, 'data')
  view.setUint32(40, dataLen, true)

  let offset = 44
  for (const f of frames) {
    new Uint8Array(buffer, offset, f.byteLength).set(new Uint8Array(f))
    offset += f.byteLength
  }
  return new Blob([buffer], { type: 'audio/wav' })
}
