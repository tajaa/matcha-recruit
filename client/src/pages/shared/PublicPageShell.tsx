import type { ReactNode } from 'react'

// Lifted from the public token-signing pages (SignPolicy /
// SignEmployeeDocument), which each carried an identical local `Shell`.
// Centered dark card; `wide` widens it for the document-review form stage.
export function PublicPageShell({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-10">
      <div className={`${wide ? 'max-w-xl' : 'max-w-md'} w-full text-center`}>{children}</div>
    </div>
  )
}
