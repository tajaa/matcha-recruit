import { AdminButton, AdminInput, AdminSelect, AdminTable, AdminTextarea } from './AdminUI'
import { AdminTabs } from './AdminTabs'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

describe('shared admin controls', () => {
  it('keeps native form validation, labels, values, and submit behavior', async () => {
    const submit = vi.fn()
    function Form() {
      const [plan, setPlan] = useState('lite')
      return <form onSubmit={(event) => { event.preventDefault(); submit(Object.fromEntries(new FormData(event.currentTarget))) }}>
        <AdminInput label="Token limit" name="limit" type="number" min={1} max={100} required defaultValue="10" />
        <AdminSelect label="Plan" name="plan" value={plan} onChange={(event) => setPlan(event.target.value)} options={[{ value: 'lite', label: 'Lite' }, { value: 'pro', label: 'Pro' }]} />
        <AdminTextarea label="Notes" name="notes" defaultValue="Keep this record" />
        <AdminButton type="submit">Save</AdminButton>
      </form>
    }
    render(<Form />)
    const limit = screen.getByRole('spinbutton', { name: 'Token limit' })
    expect(limit).toHaveAttribute('min', '1')
    expect(limit).toHaveAttribute('max', '100')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Plan' }), 'pro')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(submit).toHaveBeenCalledWith({ limit: '10', plan: 'pro', notes: 'Keep this record' })
    await userEvent.clear(limit)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(submit).toHaveBeenCalledTimes(1)
  })

  it('keeps table content, column spans, and row actions intact', async () => {
    const action = vi.fn()
    render(<AdminTable><thead><tr><th>Company</th><th>Action</th></tr></thead><tbody><tr><td colSpan={2}><AdminButton onClick={action}>Restore customer</AdminButton></td></tr></tbody></AdminTable>)
    expect(screen.getByRole('cell')).toHaveAttribute('colspan', '2')
    await userEvent.click(screen.getByRole('button', { name: 'Restore customer' }))
    expect(action).toHaveBeenCalledOnce()
  })

  it('changes local views without submitting a surrounding form', async () => {
    const change = vi.fn(), submit = vi.fn()
    render(<form onSubmit={submit}><AdminTabs label="Account views" options={[{ value: 'all', label: 'All' }, { value: 'active', label: 'Active' }, { value: 'disabled', label: 'Unavailable', disabled: true }]} value="all" onChange={change} /></form>)
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Active' }))
    await userEvent.click(screen.getByRole('button', { name: 'Unavailable' }))
    expect(change).toHaveBeenCalledExactlyOnceWith('active')
    expect(submit).not.toHaveBeenCalled()
  })
})
