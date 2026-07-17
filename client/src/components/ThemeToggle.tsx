import { useState } from 'react'
import { Sun, Moon } from 'lucide-react'
import { getTheme, setTheme, type AppTheme } from '../utils/theme'

/** Dark ⇄ light switch. Lives in every sidebar footer (SidebarShell default),
 *  where it sits in a row of icon controls alongside settings and log out —
 *  hence icon-only, with the label carried by the tooltip. */
export default function ThemeToggle() {
  const [theme, setThemeState] = useState<AppTheme>(getTheme())

  function toggle() {
    const next: AppTheme = theme === 'dark' ? 'light' : 'dark'
    setThemeState(next)
    setTheme(next)
  }

  const Icon = theme === 'dark' ? Sun : Moon
  const label = theme === 'dark' ? 'Light mode' : 'Dark mode'

  return (
    <button
      type="button"
      onClick={toggle}
      title={label}
      aria-label={label}
      className="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-800/60 hover:text-zinc-300"
    >
      <Icon className="h-4 w-4" strokeWidth={1.5} />
    </button>
  )
}
