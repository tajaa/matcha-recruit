import type { MWProject } from '../../../types'
import type { PresenceMember } from '../../../api/projectSocket'
import type { RemoteCaret } from '../../../hooks/useProjectPresence'

export interface CollabProps {
  // Real-time collaborator presence (optional). When passed in from
  // ProjectView via useProjectPresence, the SectionEditor renders remote
  // carets for each member and reports its own caret on selection change.
  selfId?: string
  members?: PresenceMember[]
  remoteCarets?: Map<string, RemoteCaret>
  onCaretChange?: (sectionId: string, anchor: number, head: number) => void
}

export interface ProjectPanelPropsLegacy extends CollabProps {
  state: Record<string, unknown>
  threadId: string
  lightMode: boolean
  streaming: boolean
  onStateUpdate: (state: Record<string, unknown>, version: number) => void
  projectId?: undefined
  project?: undefined
  onProjectUpdate?: undefined
}

export interface ProjectPanelPropsNew extends CollabProps {
  projectId: string
  project: MWProject
  onProjectUpdate: (project: MWProject) => void
  state?: undefined
  threadId?: undefined
  lightMode?: boolean
  streaming?: boolean
  onStateUpdate?: undefined
}

export type ProjectPanelProps = ProjectPanelPropsLegacy | ProjectPanelPropsNew
