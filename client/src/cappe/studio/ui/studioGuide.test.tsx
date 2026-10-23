import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { COMMANDS } from './commands'
import { GUIDE, GUIDE_SEEN_KEY, guideSeen, markGuideSeen } from './guideContent'
import StudioGuide from './StudioGuide'

afterEach(() => { try { window.localStorage.clear() } catch { /* storage off */ } })

describe('the Studio guide', () => {
  it('opens at the section asked for, and goes forward, back and to any section', () => {
    render(<StudioGuide section="picture" onClose={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Edit a picture' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next: Cut something out' }))
    expect(screen.getByRole('heading', { name: 'Cut something out' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    expect(screen.getByRole('heading', { name: 'Edit a picture' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Contents' })).getByRole('button', { name: 'Text that flows' }))
    expect(screen.getByRole('heading', { name: 'Text that flows' })).toBeInTheDocument()
  })

  it('keeps the keyboard while open: arrows page, Esc closes, nothing behind it sees a key', () => {
    const onClose = vi.fn()
    const behind = vi.fn()
    window.addEventListener('keydown', behind)
    render(<StudioGuide section="start" onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByRole('heading', { name: GUIDE[1].title })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'z', metaKey: true })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(behind).not.toHaveBeenCalled()
    window.removeEventListener('keydown', behind)
  })

  it('lists every command that has a key, as the menus show it', () => {
    render(<StudioGuide section="keys" onClose={() => {}} />)
    for (const c of COMMANDS.filter((x) => x.keys)) {
      expect(screen.getAllByText(c.label).length).toBeGreaterThan(0)
    }
    expect(screen.getByText('Edit picture…').closest('tr')).toHaveTextContent('⇧⌘E')
  })

  it('names each tool with the key the Studio really uses', () => {
    const tools = GUIDE.find((s) => s.id === 'tools')!.points!.join('\n')
    for (const c of COMMANDS.filter((x) => x.id.startsWith('tool-'))) {
      expect(tools).toContain(`${c.label} (${c.keys})`)
    }
  })

  it('every section has words and a unique id', () => {
    expect(new Set(GUIDE.map((s) => s.id)).size).toBe(GUIDE.length)
    for (const s of GUIDE) expect(!!(s.body || s.points?.length)).toBe(true)
  })

  it('remembers it was seen, and says seen when storage is off', () => {
    expect(guideSeen()).toBe(false)
    markGuideSeen()
    expect(window.localStorage.getItem(GUIDE_SEEN_KEY)).toBe('1')
    expect(guideSeen()).toBe(true)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('off') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('off') })
    expect(guideSeen()).toBe(true)
    expect(() => markGuideSeen()).not.toThrow()
  })
})
