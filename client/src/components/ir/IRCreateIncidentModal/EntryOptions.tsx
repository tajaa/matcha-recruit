import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mic, MessageCircle, Square, Loader2, Sparkles, AlertTriangle } from 'lucide-react'
import { api, ApiError } from '../../../api/client'
import { useVoiceDictation } from '../../../hooks/useVoiceDictation'
import { fmtElapsed, type LocationRow } from './shared'
import type { VoicePrefill } from '../../../types/ir'

type Prefill = {
  reported_by_name?: string | null
  occurred_at_text?: string | null
  location_id?: string | null
  description?: string | null
  witnesses?: { name: string }[]
}

type Props = {
  canDictate: boolean
  canChat: boolean
  showDictateUpsell: boolean
  locations: LocationRow[] | null
  onClose: () => void
  onPrefill: (prefill: Prefill, meta?: { voiceTranscript?: string }) => void
  onOpenChat: () => void
}

export function EntryOptions({ canDictate, canChat, showDictateUpsell, locations, onClose, onPrefill, onOpenChat }: Props) {
  const [transcribing, setTranscribing] = useState(false)
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null)
  const [voiceHint, setVoiceHint] = useState<{ type?: string; severity?: string } | null>(null)
  const [locationMissing, setLocationMissing] = useState(false)

  async function finishDictation() {
    const wav = await dictation.stop()
    if (!wav) { setVoiceMsg('No audio captured — try again.'); return }
    setTranscribing(true)
    setVoiceMsg(null)
    try {
      const fd = new FormData()
      fd.append('file', wav, 'dictation.wav')
      const p = await api.upload<VoicePrefill>('/ir/incidents/voice/parse', fd)
      if (!p.available) { setVoiceMsg("Couldn't understand the audio — please type the details."); return }
      onPrefill(
        {
          reported_by_name: p.reported_by_name,
          occurred_at_text: p.occurred_at_text,
          location_id: p.location_id,
          description: p.description,
          witnesses: p.witnesses,
        },
        { voiceTranscript: p.transcript ?? undefined },
      )
      setVoiceHint(p.incident_type || p.severity ? { type: p.incident_type ?? undefined, severity: p.severity ?? undefined } : null)
      const voiceLoc = p.location_id && (locations || []).some((l) => l.id === p.location_id) ? p.location_id : null
      setLocationMissing(!voiceLoc && (locations?.length ?? 0) > 1)
    } catch (err) {
      const tooMany = err instanceof ApiError && err.status === 429
      setVoiceMsg(tooMany
        ? 'Too many dictation attempts — wait a moment, or just type the details.'
        : 'Transcription failed — please type the details.')
    } finally {
      setTranscribing(false)
    }
  }

  const dictation = useVoiceDictation({ maxDurationSeconds: 120, onMaxDuration: () => { void finishDictation() } })

  if (!canDictate && !canChat && !showDictateUpsell) return null

  return (
    <div className="space-y-2">
      {canDictate && (
        dictation.status === 'recording' ? (
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
          <div className={canChat ? 'grid grid-cols-1 gap-2 sm:grid-cols-2' : ''}>
            <button type="button" onClick={() => { setVoiceMsg(null); setVoiceHint(null); setLocationMissing(false); void dictation.start() }}
              className="group flex w-full items-center gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] px-4 py-3 text-left transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/[0.1]">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300 transition-colors group-hover:bg-emerald-500/25">
                <Mic className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-zinc-100">Dictate this report</span>
                <span className="block text-[12px] text-zinc-400">Talk it through — AI fills the form.</span>
              </span>
            </button>
            {canChat && (
              <button type="button" onClick={onOpenChat}
                className="group flex w-full items-center gap-3 rounded-xl border border-sky-500/25 bg-sky-500/[0.06] px-4 py-3 text-left transition-colors hover:border-sky-500/40 hover:bg-sky-500/[0.1]">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sky-500/15 text-sky-300 transition-colors group-hover:bg-sky-500/25">
                  <MessageCircle className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-zinc-100">Talk it through with AI</span>
                  <span className="block text-[12px] text-zinc-400">Chat back and forth — AI fills the form.</span>
                </span>
              </button>
            )}
          </div>
        )
      )}

      {!canDictate && canChat && (
        <button type="button" onClick={onOpenChat}
          className="group flex w-full items-center gap-3 rounded-xl border border-sky-500/25 bg-sky-500/[0.06] px-4 py-3 text-left transition-colors hover:border-sky-500/40 hover:bg-sky-500/[0.1]">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sky-500/15 text-sky-300 transition-colors group-hover:bg-sky-500/25">
            <MessageCircle className="h-4 w-4" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-medium text-zinc-100">Talk it through with AI</span>
            <span className="block text-[12px] text-zinc-400">Chat back and forth — AI fills the form.</span>
          </span>
        </button>
      )}

      {(canDictate || canChat) && (
        <p className="px-0.5 text-[11px] text-zinc-500">AI-assisted — every field stays editable. This becomes a legal record.</p>
      )}
      {dictation.status === 'denied' && <p className="px-0.5 text-[11px] text-amber-400">Microphone access denied — enable it in your browser settings, or just type the report below.</p>}
      {dictation.status === 'error' && <p className="px-0.5 text-[11px] text-amber-400">Couldn't start recording — please type the report below.</p>}
      {voiceMsg && <p className="px-0.5 text-[11px] text-amber-400">{voiceMsg}</p>}
      {locationMissing && (
        <p className="flex items-start gap-1.5 px-0.5 text-[11px] text-amber-400">
          <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
          <span>We didn't catch the location — pick it when you reach that step.</span>
        </p>
      )}
      {voiceHint && (
        <div className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/20 bg-emerald-500/[0.06] px-2 py-1 text-[11px] text-emerald-300">
          <Sparkles className="h-3 w-3" />
          AI suggestion: {[voiceHint.type, voiceHint.severity].filter(Boolean).join(' · ')}
          <span className="text-emerald-400/50">· confirmed after submit</span>
        </div>
      )}

      {showDictateUpsell && (
        <Link
          to="/app/company#addons"
          onClick={onClose}
          className="group flex w-full items-center gap-3 rounded-xl border border-white/[0.08] bg-zinc-800/30 px-4 py-3 text-left transition-colors hover:border-white/15"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-zinc-500 transition-colors group-hover:text-zinc-300">
            <Mic className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium text-zinc-300">Dictate this report</span>
            <span className="block text-[12px] text-zinc-500">Talk it through — AI fills the form for you.</span>
          </span>
          <span className="text-[8.5px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/20 leading-none">
            Add-on
          </span>
        </Link>
      )}

      {(canDictate || canChat || showDictateUpsell) && (
        <div className="flex items-center gap-3 pt-0.5">
          <div className="h-px flex-1 bg-white/[0.06]" />
          <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600">Or answer step by step</span>
          <div className="h-px flex-1 bg-white/[0.06]" />
        </div>
      )}
    </div>
  )
}
