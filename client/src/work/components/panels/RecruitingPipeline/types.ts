import type { MWProject } from '../../../types'

export type Tab = 'status' | 'posting' | 'candidates' | 'interviews' | 'shortlist' | 'offer'
export type SortKey = 'name' | 'experience_years' | 'location' | 'match_score'

export interface RecruitingPipelineProps {
  project: MWProject
  projectId: string
  onUpdate: (project: MWProject) => void
  streaming?: boolean
  onSendInterviews?: (candidateIds: string[], positionTitle?: string) => Promise<void>
  onSyncInterviews?: () => Promise<void>
  onAnalyzeCandidates?: () => Promise<void>
  onPromptChat?: (placeholders: PlaceholderInfo[]) => void
  offerPdfUrl?: string | null
}

export interface PlaceholderInfo {
  placeholder: string  // e.g. "[Number]"
  label: string        // e.g. "Number of locations"
}
