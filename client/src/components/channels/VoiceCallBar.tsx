import { useRef, useEffect } from 'react'
import { Phone, PhoneOff, Mic, MicOff, Camera, CameraOff, Loader2 } from 'lucide-react'

interface VoiceCallBarProps {
  callState: 'idle' | 'joining' | 'active'
  participants: { userId: string; name: string; isSpeaking: boolean; stream: MediaStream | null }[]
  isMuted: boolean
  isVideoEnabled: boolean
  elapsedSeconds: number
  localStream: MediaStream | null
  onJoin: () => void
  onLeave: () => void
  onToggleMute: () => void
  onToggleVideo: () => void
  activeCallUsers?: { user_id: string; name: string }[]
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function VideoTile({ stream, muted, label, isSpeaking, isSelf }: {
  stream: MediaStream | null
  muted?: boolean
  label: string
  isSpeaking?: boolean
  isSelf?: boolean
}) {
  const ref = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (ref.current) {
      ref.current.srcObject = stream
    }
  }, [stream])

  const hasVideo = stream?.getVideoTracks().some(t => t.enabled) ?? false

  return (
    <div className={`relative overflow-hidden rounded-lg bg-zinc-800 aspect-video ${
      isSpeaking ? 'ring-2 ring-emerald-400' : ''
    }`}>
      <video
        ref={ref}
        autoPlay
        playsInline
        muted={muted}
        className={`w-full h-full object-cover ${hasVideo ? '' : 'opacity-0 absolute inset-0'} ${isSelf ? 'mirror' : ''}`}
        style={isSelf ? { transform: 'scaleX(-1)' } : undefined}
      />
      {!hasVideo && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className={`w-12 h-12 rounded-full flex items-center justify-center text-lg font-medium ${
            isSpeaking ? 'bg-emerald-600/40 text-emerald-300' : 'bg-zinc-700 text-zinc-400'
          }`}>
            {label.charAt(0).toUpperCase()}
          </div>
        </div>
      )}
      <div className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-black/60 text-[10px] text-zinc-300 font-medium">
        {label}{isSelf ? ' (You)' : ''}
      </div>
    </div>
  )
}

export default function VoiceCallBar({
  callState,
  participants,
  isMuted,
  isVideoEnabled,
  elapsedSeconds,
  localStream,
  onJoin,
  onLeave,
  onToggleMute,
  onToggleVideo,
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

  // State C: In call — video grid + controls
  if (callState === 'active') {
    const totalTiles = participants.length + 1 // participants + self
    const gridCols = totalTiles <= 2 ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-2'

    return (
      <div className="border-b border-emerald-900/40 bg-zinc-900/95 shrink-0">
        {/* Video grid */}
        <div className={`grid ${gridCols} gap-1 p-2 max-h-[50vh] overflow-hidden`}>
          {/* Remote participants */}
          {participants.map((p) => (
            <VideoTile
              key={p.userId}
              stream={p.stream}
              label={p.name}
              isSpeaking={p.isSpeaking}
            />
          ))}
          {/* Self-view */}
          <VideoTile
            stream={localStream}
            muted
            label="You"
            isSelf
          />
        </div>

        {/* Controls bar */}
        <div className="flex items-center gap-2 px-4 h-11 border-t border-zinc-800/50">
          {/* Voice label */}
          <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400 shrink-0">
            <span className="w-2 h-2 bg-emerald-500 rounded-full" />
            Call
          </span>

          <div className="w-px h-5 bg-zinc-700/50 mx-1" />

          {/* Participant count */}
          <span className="text-xs text-zinc-500">
            {participants.length + 1} participant{participants.length !== 0 ? 's' : ''}
          </span>

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

          {/* Video toggle */}
          <button
            onClick={onToggleVideo}
            className={`p-1.5 rounded-md transition-colors shrink-0 ${
              !isVideoEnabled
                ? 'bg-red-600/20 text-red-400 hover:bg-red-600/30'
                : 'bg-blue-600/20 text-blue-400 hover:bg-blue-600/30'
            }`}
            title={isVideoEnabled ? 'Turn off camera' : 'Turn on camera'}
          >
            {isVideoEnabled ? <Camera size={14} /> : <CameraOff size={14} />}
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
      </div>
    )
  }

  // idle with no active call users -- render nothing
  return null
}
