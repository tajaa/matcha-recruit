import type { MWProject, ResearchTask } from '../../../types'

export interface Props {
  project: MWProject
  projectId: string
  onUpdate: (project: MWProject) => void
}

export interface TaskCardProps {
  task: ResearchTask
  projectId: string
  expanded: boolean
  onToggle: () => void
  onUpdate: (p: MWProject) => void
}
