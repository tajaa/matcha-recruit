import type { ReactElement, ReactNode } from 'react';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  /** Wrap component in a router. Default: true */
  withRouter?: boolean;
  /** Initial route for MemoryRouter. If provided, uses MemoryRouter instead of BrowserRouter */
  initialEntries?: string[];
}

/**
 * Custom render function that wraps components with common providers.
 * Use this instead of @testing-library/react's render.
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    withRouter = true,
    initialEntries,
    ...renderOptions
  }: CustomRenderOptions = {}
): RenderResult & { user: ReturnType<typeof userEvent.setup> } {
  const user = userEvent.setup();

  const Wrapper = ({ children }: { children: ReactNode }) => {
    if (!withRouter) {
      return <>{children}</>;
    }

    // Use MemoryRouter if initial entries provided (better for testing specific routes)
    if (initialEntries) {
      return <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>;
    }

    return <BrowserRouter>{children}</BrowserRouter>;
  };

  return {
    user,
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  };
}

// Re-export everything from testing-library
export * from '@testing-library/react';
export { userEvent };

// Export custom render as default render
export { renderWithProviders as render };
