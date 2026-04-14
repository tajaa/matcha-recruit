import { Component, useEffect, useRef, type ErrorInfo, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { reportReactError } from '../api/errorReporter'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  // Bump this key to force the boundary to reset its error state
  resetKey?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

class ErrorBoundaryInner extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    reportReactError(error, info.componentStack ?? undefined)
    if (import.meta.env.DEV) {
      console.error('[ErrorBoundary]', error, info.componentStack)
    }
  }

  componentDidUpdate(prevProps: Props): void {
    // Reset error state when the route-derived resetKey changes
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null })
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-200 p-6">
          <div className="max-w-md text-center">
            <h1 className="text-xl font-semibold mb-2">Something went wrong</h1>
            <p className="text-sm text-zinc-400 mb-4">
              The error has been reported automatically. Try reloading the page or navigating away.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

/** Route-aware wrapper — resets the error boundary when the user navigates,
 * so a crash on one page doesn't stick when the user clicks elsewhere. */
export function ErrorBoundary({ children, fallback }: Omit<Props, 'resetKey'>) {
  const location = useLocation()
  const prevPathRef = useRef(location.pathname)

  useEffect(() => {
    prevPathRef.current = location.pathname
  }, [location.pathname])

  return (
    <ErrorBoundaryInner resetKey={location.pathname} fallback={fallback}>
      {children}
    </ErrorBoundaryInner>
  )
}
