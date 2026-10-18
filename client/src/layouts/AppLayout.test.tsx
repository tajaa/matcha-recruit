import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import AppLayout from './AppLayout'

vi.mock('../hooks/useMe', () => ({ useMe: () => ({ loading: false, authFailed: false, isPersonal: false }) }))
vi.mock('../data/pageHelp', () => ({ resolvePageHelp: () => null }))

afterEach(() => {
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('data-app-shell-bg')
  localStorage.clear()
})

describe('admin appearance', () => {
  it.each([null, 'light'])('uses dark mode and restores the previous %s theme on exit', (theme) => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('matcha_theme', theme ?? 'dark')
    const { unmount } = render(<MemoryRouter><AppLayout sidebar={null} variant="admin" /></MemoryRouter>)
    expect(document.documentElement).not.toHaveAttribute('data-theme')
    expect(document.documentElement).toHaveAttribute('data-app-shell-bg', 'admin')
    expect(localStorage.getItem('matcha_theme')).toBe(theme ?? 'dark')
    unmount()
    expect(document.documentElement.getAttribute('data-theme')).toBe(theme)
    expect(document.documentElement).not.toHaveAttribute('data-app-shell-bg')
  })

  it('restores the other app theme when leaving admin without remounting the shell', () => {
    document.documentElement.setAttribute('data-theme', 'light')
    const { rerender } = render(<MemoryRouter><AppLayout sidebar={null} variant="admin" /></MemoryRouter>)
    rerender(<MemoryRouter><AppLayout sidebar={null} /></MemoryRouter>)
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(document.documentElement).toHaveAttribute('data-app-shell-bg', 'true')
  })

  it('leaves the theme alone outside admin', () => {
    document.documentElement.setAttribute('data-theme', 'light')
    const { unmount } = render(<MemoryRouter><AppLayout sidebar={null} /></MemoryRouter>)
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    unmount()
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
})
