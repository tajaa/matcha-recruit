// Flyer design assistant — brand-authenticated AI editing of a campaign's
// flyer document.
//
// Note what is NOT here: an op applier. The server validates and applies, and
// hands back the finished document (server/app/tellus/services/flyer_ai/apply.py
// explains why it is inverted from Cappe's Merlin). The client's job is to send
// the document it has and adopt the one it gets back.
import { tellusApi } from './tellusClient'
import type {
  FlyerAiSchema,
  FlyerAssistResponse,
  FlyerDesign,
  FlyerIdea,
} from './types'

export interface AssistSelection {
  layer: string
  kind?: string
  text?: string
}

export interface AssistHistoryTurn {
  role: 'user' | 'assistant'
  content: string
  ops_summary?: string
}

export const flyerAiApi = {
  assist: (campaignId: string, body: {
    message: string
    design: FlyerDesign
    history: AssistHistoryTurn[]
    selection?: AssistSelection
  }) => tellusApi.post<FlyerAssistResponse>(`/promo/campaigns/${campaignId}/design/assist`, body),

  ideas: (campaignId: string) =>
    tellusApi.post<{ ideas: FlyerIdea[] }>(`/promo/campaigns/${campaignId}/design/ideas`, {}),

  schema: () => tellusApi.get<FlyerAiSchema>('/promo/design/schema'),
}
