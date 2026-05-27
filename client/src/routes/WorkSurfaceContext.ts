import { createContext, useContext } from 'react'

// Which product surface a matcha-work page is rendering inside.
//   'werk'        — personal product (role='individual'), served at /werk
//   'matcha-work' — business product (inside a Matcha company), served at /work
//
// IMPORTANT: feature gating (Plus, HR skills, Node/Compliance/Payer modes,
// recruiting) stays keyed on identity (isPersonal / role==='individual'), NOT on
// surface. Surface drives ONLY branding strings and in-tree navigation base paths.
// It is the seam for eventually extracting Werk to its own site.
//
// Default is 'matcha-work' so any accidental out-of-tree render is harmless and
// business-branded. Kept dependency-free (react only) to avoid an import cycle
// with WorkLayout.
export type WorkSurface = 'matcha-work' | 'werk'

export const WorkSurfaceContext = createContext<WorkSurface>('matcha-work')
export const WorkSurfaceProvider = WorkSurfaceContext.Provider

export function useWorkSurface(): WorkSurface {
  return useContext(WorkSurfaceContext)
}

export function useWorkBrand(): 'Werk' | 'Matcha-Work' {
  return useWorkSurface() === 'werk' ? 'Werk' : 'Matcha-Work'
}

export function useWorkBase(): '/werk' | '/work' {
  return useWorkSurface() === 'werk' ? '/werk' : '/work'
}
