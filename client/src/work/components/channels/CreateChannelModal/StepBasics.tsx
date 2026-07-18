import { Globe, Lock, UserPlus } from 'lucide-react'

/* ─── Step 1: Basics ─── */

export function StepBasics({
  name, setName, description, setDescription, visibility, setVisibility,
}: {
  name: string
  setName: (v: string) => void
  description: string
  setDescription: (v: string) => void
  visibility: 'public' | 'invite_only' | 'private'
  setVisibility: (v: 'public' | 'invite_only' | 'private') => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs text-zinc-400 mb-1">Channel name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. premium-insights, coaching-circle"
          maxLength={100}
          autoFocus
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-400 mb-1">Description (optional)</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What's this channel about?"
          rows={2}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none"
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-400 mb-1.5">Visibility</label>
        <div className="flex gap-2">
          {([
            { value: 'public' as const, icon: Globe, label: 'Public', desc: 'Listed; anyone can join' },
            { value: 'invite_only' as const, icon: UserPlus, label: 'Invite Only', desc: 'Listed; invite required' },
            { value: 'private' as const, icon: Lock, label: 'Private', desc: 'Hidden; invite required' },
          ]).map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setVisibility(opt.value)}
              className={`flex-1 flex flex-col items-center gap-1 px-2 py-2.5 rounded-lg border text-[11px] transition-colors ${
                visibility === opt.value
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400'
                  : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
              }`}
            >
              <opt.icon size={14} />
              <span className="font-medium">{opt.label}</span>
              <span className="text-[9px] opacity-70 leading-tight text-center">{opt.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
