import { api } from '../../client'
import type {
  RegulatoryQAResponse,
  ProtocolAnalysisResult,
  PolicyDraftResult,
} from './types'

// ── Regulatory Q&A ──

export function askRegulatoryQuestion(question: string, locationId?: string): Promise<RegulatoryQAResponse> {
  return api.post<RegulatoryQAResponse>('/compliance/ask', {
    question,
    location_id: locationId,
  })
}

// ── Protocol Gap Analysis ──

export function analyzeProtocol(
  protocolText: string,
  locationId?: string,
  categories?: string[],
): Promise<ProtocolAnalysisResult> {
  return api.post<ProtocolAnalysisResult>('/compliance/protocol-analysis', {
    protocol_text: protocolText,
    location_id: locationId,
    categories,
  })
}

// ── Policy Drafting ──

export function draftPolicy(
  topic: string,
  jurisdiction: string,
  locationId?: string,
  industryContext?: string,
): Promise<PolicyDraftResult> {
  return api.post<PolicyDraftResult>('/policies/draft', {
    topic,
    jurisdiction,
    location_id: locationId,
    industry_context: industryContext,
  })
}
