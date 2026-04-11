import { Phone, PhoneOff, Mic, MicOff, Loader2 } from 'lucide-react'

interface VoiceCallBarProps {
  callState: 'idle' | 'joining' | 'active'
  participants: { userId: string; name: string; isSpeaking: boolean }[]
  isMuted: boolean
  elapsedSeconds: number
  onJoin: () => void
  onLeave: () => void
  onToggleMute: () => void
  activeCallUsers?: { user_id: string; name: string }[]
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export default function VoiceCallBar({
  callState,
  participants,
  isMuted,
  elapsedSeconds,
  onJoin,
  onLeave,
  onToggleMute,
  activeCallUsers,
}: VoiceCallBarProps) {
  // State A: Call available but not joined
  if (callState === 'idle' && activeCallUsers && activeCallUsers.length > 0) {
    const names = activeCallUsers.map((u) => u.name).join(', ')
    return (
      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800/50 bg-zinc-900/80 text-sm">
        <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse shrink-0" />
        <span className="text-zinc-400 truncate">
          Voice call active &mdash; <span className="text-zinc-300">{names}</span>. Join?
        </span>
        <button
          onClick={onJoin}
          className="ml-auto flex items-center gap-1.5 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-md transition-colors shrink-0"
        >
          <Phone size={12} />
          Join
        </button>
      </div>
    )
  }

  // State B: Joining
  if (callState === 'joining') {
    return (
      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800/50 bg-zinc-900/80 text-sm">
        <Loader2 size={14} className="animate-spin text-emerald-400 shrink-0" />
        <span className="text-zinc-400">Connecting...</span>
      </div>
    )
  }

  // State C: In call
  if (callState === 'active') {
    return (
      <div className="flex items-center gap-2 px-4 h-11 border-b border-emerald-900/40 bg-zinc-900/95 shrink-0">
        {/* Voice label */}
        <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400 shrink-0">
          <span className="w-2 h-2 bg-emerald-500 rounded-full" />
          Voice
        </span>

        <div className="w-px h-5 bg-zinc-700/50 mx-1" />

        {/* Participant circles */}
        <div className="flex items-center gap-1.5 min-w-0">
          {participants.map((p) => (
            <div
              key={p.userId}
              className={`relative w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-medium shrink-0 ${
                p.isSpeaking
                  ? 'bg-emerald-600/30 text-emerald-300'
                  : 'bg-zinc-700/60 text-zinc-400'
              }`}
              title={p.name}
            >
              {/* Speaking ring */}
              {p.isSpeaking && (
                <span className="absolute inset-0 rounded-full border-2 border-emerald-400 animate-pulse" />
              )}
              {p.name.charAt(0).toUpperCase()}
            </div>
          ))}
        </div>

        {/* Timer */}
        <span className="text-xs text-zinc-500 tabular-nums ml-auto shrink-0">
          {formatTime(elapsedSeconds)}
        </span>

        {/* Mute toggle */}
        <button
          onClick={onToggleMute}
          className={`p-1.5 rounded-md transition-colors shrink-0 ${
            isMuted
              ? 'bg-red-600/20 text-red-400 hover:bg-red-600/30'
              : 'bg-blue-600/20 text-blue-400 hover:bg-blue-600/30'
          }`}
          title={isMuted ? 'Unmute' : 'Mute'}
        >
          {isMuted ? <MicOff size={14} /> : <Mic size={14} />}
        </button>

        {/* Leave call */}
        <button
          onClick={onLeave}
          className="p-1.5 rounded-md bg-red-600/20 text-red-400 hover:bg-red-600/30 transition-colors shrink-0"
          title="Leave call"
        >
          <PhoneOff size={14} />
        </button>
      </div>
    )
  }

  // idle with no active call users -- render nothing
  return null
}
