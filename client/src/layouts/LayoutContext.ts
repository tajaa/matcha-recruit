import { createContext, useContext } from 'react'

/** Shell state for the sidebar rail. `hasTopNav` lived here to tell SidebarShell
 *  whether AppLayout's top bar was already showing the logo; the bar is gone and
 *  the rail always renders its own masthead, so the flag had no readers left. */
export const LayoutContext = createContext<{
  sidebarCollapsed: boolean
  setSidebarCollapsed: (v: boolean) => void
}>({
  sidebarCollapsed: false,
  setSidebarCollapsed: () => {},
})
export const useLayoutContext = () => useContext(LayoutContext)
