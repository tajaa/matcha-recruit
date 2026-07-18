import { FileText, Presentation, Users, X } from 'lucide-react'

interface Props {
  onClose: () => void
  onCreate: (type: 'general' | 'presentation' | 'recruiting') => void
}

export default function ProjectTypePickerModal({ onClose, onCreate }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-w-surface border border-w-line rounded-xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">New Project</h2>
          <button onClick={onClose} className="text-w-dim hover:text-white">
            <X size={16} />
          </button>
        </div>
        <p className="text-w-dim text-sm mb-4">What kind of project?</p>
        <div className="space-y-2">
          {([
            { type: 'general' as const, icon: FileText, label: 'Research / Report', desc: 'Build documents and plans from chat' },
            { type: 'presentation' as const, icon: Presentation, label: 'Presentation', desc: 'Create slide decks and pitch materials' },
            { type: 'recruiting' as const, icon: Users, label: 'Job Posting', desc: 'Recruiting pipeline with resumes and interviews' },
          ]).map((opt) => (
            <button
              key={opt.type}
              onClick={() => onCreate(opt.type)}
              className="w-full flex items-center gap-3 p-3 rounded-lg border border-w-line hover:border-w-accent hover:bg-w-surface2/60 transition-colors text-left"
            >
              <opt.icon size={20} className="text-w-accent shrink-0" />
              <div>
                <p className="text-sm font-medium text-white">{opt.label}</p>
                <p className="text-xs text-w-dim">{opt.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
