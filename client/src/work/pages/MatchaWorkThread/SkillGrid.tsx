import { HR_SKILLS, PERSONAL_SKILLS } from './constants'
import type { ThreadTheme } from './theme'

interface SkillGridProps {
  isIndividual: boolean
  isProject: boolean
  lightMode: boolean
  th: ThreadTheme
  setInput: (v: string) => void
  textareaRef: React.RefObject<HTMLTextAreaElement>
  setShowTutorSetup: (v: boolean) => void
  setTutorDismissed: (v: boolean) => void
}

export default function SkillGrid({
  isIndividual, isProject, lightMode, th, setInput, textareaRef, setShowTutorSetup, setTutorDismissed,
}: SkillGridProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <p className={`text-sm font-medium mb-4 ${isProject ? 'text-[#e8e8e8]' : th.emptyText}`}>
        What would you like to work on?
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-w-md w-full">
        {(isIndividual ? PERSONAL_SKILLS : HR_SKILLS).filter((s) => !s.requiresCompany || !isIndividual).map((skill) => {
          const Icon = skill.icon
          return (
            <button
              key={skill.id}
              onClick={() => {
                if (skill.id === 'language_tutor') {
                  setShowTutorSetup(true)
                  setTutorDismissed(false)
                  return
                }
                if (skill.prompt) {
                  setInput(skill.prompt)
                  textareaRef.current?.focus()
                }
              }}
              className={`flex flex-col items-center gap-1.5 rounded-lg px-3 py-3 text-center transition-colors ${
                isProject
                  ? 'bg-[#252526] hover:bg-[#2a2d2e] text-[#d4d4d4]'
                  : lightMode
                    ? 'bg-zinc-100 hover:bg-zinc-200 text-zinc-600'
                    : 'bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400'
              }`}
            >
              <Icon size={16} className={isProject ? 'text-[#ce9178]' : 'text-emerald-500'} />
              <span className="text-[11px] font-medium">{skill.label}</span>
              <span className={`text-[9px] leading-tight ${isProject ? 'text-[#6a737d]' : lightMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
                {'dropHint' in skill ? skill.dropHint : skill.desc}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
