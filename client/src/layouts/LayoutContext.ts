import { createContext, useContext } from 'react'

export const LayoutContext = createContext({ hasTopNav: false, sidebarCollapsed: false })
export const useLayoutContext = () => useContext(LayoutContext)
