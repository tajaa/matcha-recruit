import { useState } from 'react'
import { Sun, Moon } from 'lucide-react'
import { useLayoutContext } from '../layouts/LayoutContext'
import { getBrokerTheme, setBrokerTheme, type BrokerTheme } from '../utils/brokerTheme'

/** Dark ⇄ light switch for the Broker Portal. Lives in the sidebar footer. */
export default function BrokerThemeToggle() {
  const { sidebarCollapsed } = useLayoutContext()
  const [theme, setTheme] = useState<BrokerTheme>(getBrokerTheme())

  function toggle() {
    const next: BrokerTheme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setBrokerTheme(next)
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
