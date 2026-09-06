import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CredentialManager } from './CredentialManager'

const manager = vi.hoisted(() => ({
  reclassify: vi.fn(),
  useCredentialManager: vi.fn(),
}))

vi.mock('./useCredentialManager', () => ({
  DOC_TYPE_LABELS: {
    medical_license: 'Professional License',
    food_handler_card: 'Food Handler Card',
    other: 'Other Document',
  },
  useCredentialManager: manager.useCredentialManager,
}))

const customRequirement = {
  id: 'requirement-1',
  employee_id: 'employee-1',
  credential_type_id: 'custom-type-1',
  template_id: null,
  status: 'pending' as const,
  is_required: true,
  priority: 'blocking',
  due_date: null,
  onboarding_task_id: null,
  credential_document_id: null,
  verified_at: null,
  expires_at: null,
  waived_at: null,
  waiver_reason: null,
  notes: null,
  created_at: '2026-09-03T00:00:00Z',
  credential_type_key: 'custom_forklift',
  credential_type_label: 'Forklift Certification',
  credential_type_category: 'clearance',
  has_expiration: true,
  has_number: false,
  has_state: false,
}

const document = {
  id: 'document-1',
  company_id: 'company-1',
  employee_id: 'employee-1',
  document_type: 'other',
  filename: 'forklift.pdf',
  file_path: 'private/forklift.pdf',
  mime_type: 'application/pdf',
  file_size: 100,
  extracted_data: null,
  extraction_status: 'extracted',
  review_status: 'approved',
  reviewed_by: null,
  reviewed_at: null,
  review_notes: null,
  uploaded_by: null,
  uploaded_via: 'admin',
  created_at: '2026-09-03T00:00:00Z',
  updated_at: '2026-09-03T00:00:00Z',
  expires_at: null,
  is_current: true,
}

describe('CredentialManager reclassification', () => {
  beforeEach(() => {
    manager.reclassify.mockReset()
    manager.useCredentialManager.mockReset().mockReturnValue({
      credentials: null,
      loading: false,
      approve: vi.fn(),
      reject: vi.fn(),
      reclassify: manager.reclassify,
      remove: vi.fn(),
      download: vi.fn(),
      requirements: [customRequirement],
      reqLoading: false,
      editing: false,
      setEditing: vi.fn(),
      editForm: {},
      setEditForm: vi.fn(),
      confirmWord: '',
      setConfirmWord: vi.fn(),
      editSaving: false,
      editError: '',
      startEdit: vi.fn(),
      saveEdit: vi.fn(),
      docsByType: { other: [document] },
      hasRequirements: true,
      allTypes: ['custom_forklift', 'other'],
      reqByType: { custom_forklift: customRequirement },
      expirations: [],
      handleUpload: vi.fn(),
    })
  })

  it('offers requirement-backed custom types and enforces their expiration policy', () => {
    const { container } = render(<CredentialManager employeeId="employee-1" />)

    fireEvent.click(screen.getByRole('button', { name: 'Type' }))
    const select = screen.getByLabelText('Document type')
    expect(screen.getByRole('option', { name: 'Forklift Certification' })).toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'custom_forklift' } })
    const save = screen.getByRole('button', { name: 'Save type' })
    expect(save).toBeDisabled()

    const expirationInput = container.querySelector<HTMLInputElement>('input[type="date"]')
    expect(expirationInput).not.toBeNull()
    fireEvent.change(expirationInput!, {
      target: { value: '2027-06-30' },
    })
    fireEvent.click(save)

    expect(manager.reclassify).toHaveBeenCalledWith(
      'document-1',
      'custom_forklift',
      '2027-06-30',
    )
  })

  it('allows a replacement upload and shows no history section when nothing is superseded', () => {
    render(<CredentialManager employeeId="employee-1" />)

    expect(screen.getByText('Current')).toBeInTheDocument()
    expect(screen.getByText(/Add replacement credential/)).toBeInTheDocument()
    expect(screen.queryByText('History')).toBeNull()
  })

  it('lists superseded approved documents under their own type, newest first', () => {
    manager.useCredentialManager.mockReturnValue({
      ...manager.useCredentialManager(),
      docsByType: {
        other: [
          document,
          {
            ...document,
            id: 'document-older',
            filename: 'oldest-forklift.pdf',
            reviewed_at: '2026-01-01T00:00:00Z',
            is_current: false,
          },
          {
            ...document,
            id: 'document-newer',
            filename: 'previous-forklift.pdf',
            reviewed_at: '2026-06-01T00:00:00Z',
            is_current: false,
          },
        ],
      },
    })

    render(<CredentialManager employeeId="employee-1" />)

    // Section heading plus one badge per superseded document.
    expect(screen.getAllByText('History')).toHaveLength(3)
    const historical = screen.getAllByText(/forklift\.pdf/).map((node) => node.textContent)
    expect(historical).toEqual([
      'forklift.pdf',
      'previous-forklift.pdf',
      'oldest-forklift.pdf',
    ])
  })

  it('never offers approval on a historical document', () => {
    const expiringDocument = { ...document, document_type: 'food_handler_card' }
    manager.useCredentialManager.mockReturnValue({
      ...manager.useCredentialManager(),
      docsByType: {
        food_handler_card: [
          expiringDocument,
          { ...expiringDocument, id: 'document-history', filename: 'old-card.pdf', is_current: false },
        ],
      },
      allTypes: ['food_handler_card'],
    })

    render(<CredentialManager employeeId="employee-1" />)

    // Both documents are approved without an expiry, but only the current one
    // may be re-confirmed: approving history re-points the requirement.
    expect(screen.getAllByRole('button', { name: 'Confirm expiry' })).toHaveLength(1)
  })

  it('hides the upload zone for a type the backend would reject', () => {
    manager.useCredentialManager.mockReturnValue({
      ...manager.useCredentialManager(),
      // `other: []` keeps the generic "Other Document" upload block out of the
      // way so the assertion below is about the legacy type's own section.
      docsByType: {
        legacy_removed_type: [{ ...document, document_type: 'legacy_removed_type' }],
        other: [],
      },
      allTypes: ['legacy_removed_type'],
      reqByType: {},
      requirements: [],
    })

    render(<CredentialManager employeeId="employee-1" />)

    expect(screen.queryByText(/drop file or/)).toBeNull()
  })
})
