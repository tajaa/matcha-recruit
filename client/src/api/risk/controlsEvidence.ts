import { api } from '../client'
import type { ControlsRegister, ControlsSummary, ControlStatus } from '../../types/controlsEvidence'

export function fetchControlsRegister() {
  return api.get<ControlsRegister>('/controls-evidence/register')
}

export function fetchControlsSummary() {
  return api.get<ControlsSummary>('/controls-evidence/summary')
}

export function updateControl(
  key: string,
  payload: { status?: ControlStatus | null; note?: string | null; verified?: boolean },
) {
  return api.put<ControlsRegister>(`/controls-evidence/controls/${encodeURIComponent(key)}`, payload)
}

export function downloadControlsPacket() {
  return api.download('/controls-evidence/packet.pdf', 'proof-of-controls.pdf')
}
