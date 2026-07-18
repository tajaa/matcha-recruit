import type { Pillar } from './data'
import { InterviewMock } from './InterviewMock'
import { WorkspaceMock } from './WorkspaceMock'

export function PillarVisual({ pillar }: { pillar: Pillar }) {
  if (pillar.id === 'interviews') return <InterviewMock />
  return <WorkspaceMock />
}
