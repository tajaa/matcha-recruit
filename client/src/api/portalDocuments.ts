import { api } from './client'
import type { HandbookSectionText } from '../types/handbook'

// Documents assigned to the signed-in employee (handbooks, policies) and the
// acknowledgement flow over them. Backend: server/app/matcha/routes/employee_portal.py

export type EmployeeDocument = {
  id: string
  org_id: string
  employee_id: string
  /** `handbook:<handbook_id>:<version>` for handbook acknowledgements. */
  doc_type: string
  title: string
  description: string | null
  storage_path: string | null
  /** Mirrors backend DocumentStatus (server/app/matcha/models/employee.py). */
  status: 'draft' | 'pending_signature' | 'signed' | 'expired' | 'archived'
  /** A DATE, not a timestamp — render with formatDateOnly. */
  expires_at: string | null
  signed_at: string | null
  assigned_by: string | null
  created_at: string
  updated_at: string
}

/** Mirrors backend HandbookVersionContent. */
export type DocumentHandbookContent = {
  title: string
  version: number
  sections: HandbookSectionText[]
}

export const isHandbookDoc = (doc: EmployeeDocument) => doc.doc_type.startsWith('handbook:')

export const portalDocumentsApi = {
  list: () =>
    api.get<{ documents: EmployeeDocument[]; total: number }>('/v1/portal/me/documents'),
  get: (id: string) => api.get<EmployeeDocument>(`/v1/portal/me/documents/${id}`),
  /** Section text of the exact handbook version that was distributed. */
  handbookContent: (id: string) =>
    api.get<DocumentHandbookContent>(`/v1/portal/me/documents/${id}/handbook`),
  /** `signatureData` is the employee's typed legal name — the attestation. */
  sign: (id: string, signatureData: string) =>
    api.post<EmployeeDocument>(`/v1/portal/me/documents/${id}/sign`, {
      signature_data: signatureData,
    }),
}
