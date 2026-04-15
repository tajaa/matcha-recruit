// Web Audio synthesized notification chime. No binary asset needed.
// A short two-note ascending chime: C5 -> E5 with gentle envelope.
//
// Browser autoplay policies: AudioContext will start in 'suspended' state
// until the user has interacted with the page. We attach a one-time document
// click listener to resume it, so the first actual chime after a user gesture
// plays cleanly. Chimes triggered before any interaction are silent — which
// is the correct behavior anyway (we don't want to blast sound on page load).

let _ctx: AudioContext | null = null
let _unlocked = false

function getContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (!_ctx) {
    const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return null
    try {
      _ctx = new Ctor()
    } catch {
      return null
    }
  }
  return _ctx
}

function unlockOnce() {
  if (_unlocked) return
  const ctx = getContext()
  if (!ctx) return
  const resume = () => {
    ctx.resume().catch(() => {})
    _unlocked = true
    document.removeEventListener('pointerdown', resume)
    document.removeEventListener('keydown', resume)
  }
  document.addEventListener('pointerdown', resume, { once: true })
  document.addEventListener('keydown', resume, { once: true })
}

if (typeof window !== 'undefined') {
  unlockOnce()
}

/**
 * Play a short notification chime. Safe to call anytime — silently no-ops if
 * the AudioContext isn't available or hasn't been unlocked by a user gesture.
 */
export function playNotificationSound() {
  const ctx = getContext()
  if (!ctx || ctx.state === 'suspended') {
    // Try to resume (will succeed if we're in a gesture callback)
    ctx?.resume().catch(() => {})
    if (ctx?.state !== 'running') return
  }

  const now = ctx.currentTime
  // Two quick ascending sine notes with a soft attack and exponential decay
  playNote(ctx, 523.25, now, 0.12) // C5
  playNote(ctx, 659.25, now + 0.08, 0.18) // E5
}

function playNote(ctx: AudioContext, freq: number, startAt: number, duration: number) {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.value = freq

  // Envelope: fast attack, exponential decay. Peak modest so it doesn't startle.
  gain.gain.setValueAtTime(0.0001, startAt)
  gain.gain.exponentialRampToValueAtTime(0.12, startAt + 0.015)
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration)

  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(startAt)
  osc.stop(startAt + duration + 0.05)
}
