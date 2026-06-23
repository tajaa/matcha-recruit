import { useState } from 'react'
import { Mic, Square, Loader2 } from 'lucide-react'
import { useVoiceDictation } from '../../hooks/ir/useVoiceDictation'
import type { VoicePrefill } from '../../types/ir'

function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60)
  return `${m}:${(s % 60).toString().padStart(2, '0')}`
}

// Public (no-JWT) voice dictation for the magic-link intake forms
// (LocationIntake / AnonymousReport). Reuses the same record→WAV→Gemini-parse
// pipeline as the authed IRCreateIncidentModal, but POSTs to a token-scoped
// public parse endpoint (no Authorization header). The parent decides which
// prefill fields apply to its form via `onPrefill`. Render only when the
// company has the ir_voice_intake feature on (surfaced by the GET-validate call).
export function IRPublicDictate({
  parseUrl,
  onPrefill,
}: {
  parseUrl: string
  onPrefill: (p: VoicePrefill) => void
}) {
  const [transcribing, setTranscribing] = useState(false)
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null)

  // declared before the hook so onMaxDuration can call it (matches IRCreateIncidentModal)
  async function finishDictation() {
    const wav = await dictation.stop()
    if (!wav) {
      setVoiceMsg('No audio captured — try again.')
      return
    }
    setTranscribing(true)
    setVoiceMsg(null)
    try {
      const fd = new FormData()
      fd.append('file', wav, 'dictation.wav')
      // Plain fetch — public endpoint, no JWT (matches the form's submit fetch).
      // No Content-Type header: the browser sets the multipart boundary.
      const res = await fetch(parseUrl, { method: 'POST', body: fd })
      if (res.status === 429) {
        setVoiceMsg('Too many dictation attempts — wait a moment, or just type the details.')
        return
      }
      if (!res.ok) {
        setVoiceMsg('Transcription failed — please type the details.')
        return
      }
      const p = (await res.json()) as VoicePrefill
      if (!p.available) {
        setVoiceMsg("Couldn't understand the audio — please type the details.")
        return
      }
      onPrefill(p)
    } catch {
      setVoiceMsg('Transcription failed — please type the details.')
    } finally {
      setTranscribing(false)
    }
  }

  const dictation = useVoiceDictation({ maxDurationSeconds: 120, onMaxDuration: () => { void finishDictation() } })

  return (
    <div className="space-y-2 text-left">
      {dictation.status === 'recording' ? (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/40 bg-red-500/[0.07] px-4 py-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-500/20 text-red-300 animate-pulse">
            <Mic className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-zinc-100">Recording · {fmtElapsed(dictation.elapsedSeconds)}</div>
            <div className="text-[12px] text-red-300/80">Say who, what, when, where, and who saw it.</div>
          </div>
          <button type="button" onClick={() => { void finishDictation() }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-red-400/50 px-3 py-1.5 text-sm text-red-200 hover:bg-red-500/15 transition-colors">
            <Square className="h-3.5 w-3.5 fill-current" /> Stop
          </button>
        </div>
      ) : transcribing ? (
        <div className="flex items-center gap-3 rounded-xl border border-white/[0.08] bg-zinc-800/40 px-4 py-3 text-sm text-zinc-300">
          <Loader2 className="h-4 w-4 animate-spin text-emerald-400" /> Transcribing & filling the form…
        </div>
      ) : (
        <button type="button" onClick={() => { setVoiceMsg(null); void dictation.start() }}
          className="group flex w-full items-center gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] px-4 py-3 text-left transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/[0.1]">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300 transition-colors group-hover:bg-emerald-500/25">
            <Mic className="h-4 w-4" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-medium text-zinc-100">Dictate this report</span>
            <span className="block text-[12px] text-zinc-400">Talk it through — AI fills the form. You review every field before submitting.</span>
          </span>
        </button>
      )}

      <p className="px-0.5 text-[11px] text-zinc-500">AI-assisted — every field stays editable. This becomes a legal record.</p>
      {dictation.status === 'denied' && <p className="px-0.5 text-[11px] text-amber-400">Microphone access denied — enable it in your browser settings, or just type the report below.</p>}
      {dictation.status === 'error' && <p className="px-0.5 text-[11px] text-amber-400">Couldn't start recording — please type the report below.</p>}
      {voiceMsg && <p className="px-0.5 text-[11px] text-amber-400">{voiceMsg}</p>}
    </div>
  )
}
