import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import CappeRoutes from './routes'

describe('Cappe routes', () => {
  it.each(['/signup', '/website-setup'])('serves the signup form at %s', async (path) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path="/*" element={<CappeRoutes />} /></Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Create your Gummfit account' })).toBeInTheDocument()
  })
})
