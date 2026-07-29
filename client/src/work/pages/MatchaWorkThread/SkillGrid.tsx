import { HR_SKILLS, PERSONAL_SKILLS, HUUME_SKILLS } from './constants'
import type { ThreadTheme } from './theme'

interface SkillGridProps {
  isIndividual: boolean
  th: ThreadTheme
  huumeMode: boolean
  setInput: (v: string) => void
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  setShowTutorSetup: (v: boolean) => void
  setTutorDismissed: (v: boolean) => void
}

export default function SkillGrid({
  isIndividual, th, huumeMode, setInput, textareaRef, setShowTutorSetup, setTutorDismissed,
}: SkillGridProps) {
  const skills = huumeMode && !isIndividual ? HUUME_SKILLS : isIndividual ? PERSONAL_SKILLS : HR_SKILLS
  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <p className={`text-sm font-medium mb-4 ${th.emptyText}`}>
        What would you like to work on?
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-w-md w-full">
        {skills.filter((s) => !s.requiresCompany || !isIndividual).map((skill) => {
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
              className="flex flex-col items-center gap-1.5 rounded-lg px-3 py-3 text-center transition-colors bg-w-surface2 hover:bg-w-line text-w-dim"
            >
              <Icon size={16} className="text-w-accent" />
              <span className="text-[11px] font-medium">{skill.label}</span>
              <span className="text-[9px] leading-tight text-w-faint">
                {'dropHint' in skill ? skill.dropHint : skill.desc}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
