import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 2,   // 2 min — data stays fresh, no refetch on remount
      gcTime: 1000 * 60 * 10,     // 10 min — keep unused data in cache
      refetchOnWindowFocus: false, // don't refetch when switching tabs
      retry: 1,                    // 1 retry instead of 3
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
