import { useState } from 'react'
import { Sun, Moon } from 'lucide-react'
import { useLayoutContext } from '../layouts/LayoutContext'
import { getTheme, setTheme, type AppTheme } from '../utils/theme'

/** Dark ⇄ light switch. Lives in every sidebar footer (SidebarShell default). */
export default function ThemeToggle() {
  const { sidebarCollapsed } = useLayoutContext()
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
      className={`flex items-center w-full py-1.5 text-[12px] text-zinc-600 hover:text-zinc-200 transition-colors duration-100 group ${
        sidebarCollapsed ? 'justify-center px-0' : 'gap-2.5 px-3'
      }`}
    >
      <Icon className="h-[14px] w-[14px] text-zinc-600 group-hover:text-zinc-300" strokeWidth={1.4} />
      {!sidebarCollapsed && <span className="font-light tracking-wide">{label}</span>}
    </button>
  )
}
