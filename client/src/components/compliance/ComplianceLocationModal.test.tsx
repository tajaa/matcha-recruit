import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ComplianceLocationModal } from './ComplianceLocationModal'


describe('ComplianceLocationModal timezone status', () => {
  it('describes automatic mapping before a state is selected', () => {
    render(
      <ComplianceLocationModal
        open
        onClose={vi.fn()}
        editingLocation={null}
        jurisdictions={[]}
        onSubmit={vi.fn()}
        saving={false}
      />,
    )

    expect(screen.getByText('Select a state to map the time zone automatically.')).toBeInTheDocument()
    expect(screen.queryByText('Manual time zone')).not.toBeInTheDocument()
  })
})
