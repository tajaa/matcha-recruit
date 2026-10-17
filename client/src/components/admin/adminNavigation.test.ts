import { describe, expect, it } from 'vitest'
import { ADMIN_AREAS, adminSidebarItems, findAdminPage } from './adminNavigation'

describe('admin navigation', () => {
  it('keeps every existing sidebar destination in exactly one area', () => {
    const destinations = ADMIN_AREAS.flatMap((area) => area.pages.map((page) => page.to))
    expect(new Set(destinations).size).toBe(destinations.length)
    expect(destinations.map((to) => to.replace('/admin/', '')).sort()).toEqual([
      'updates', 'customers', 'companies', 'test-accounts', 'matcha-work',
      'matcha-ops', 'cappe', 'cappe-creators', 'fractional-hr', 'gap-analysis',
      'deal-flow', 'matcha-lite', 'products', 'pricing', 'compliance-mgmt',
      'studio', 'jurisdiction-data', 'payer-data', 'wc-rate-data', 'automation',
      'blogs', 'newsletter', 'landing-media', 'traffic', 'usage', 'client-errors',
      'server-errors', 'ai-usage', 'features', 'settings',
    ].sort())
    expect(adminSidebarItems()).toHaveLength(7)
    expect(ADMIN_AREAS.flatMap((area) => area.pages)).toHaveLength(30)
    expect(new Set(ADMIN_AREAS.map((area) => area.to)).size).toBe(7)
  })

  it.each([
    ['/admin/companies/company-1', 'Customers', '/admin/companies'],
    ['/admin/fractional-hr/client-1', 'Customers', '/admin/fractional-hr'],
    ['/admin/gap-analysis/session-1/report', 'Products & sales', '/admin/gap-analysis'],
    ['/admin/jurisdiction-data/category/wages', 'Compliance', '/admin/jurisdiction-data'],
    ['/admin/jurisdiction-data/policy/policy-1', 'Compliance', '/admin/jurisdiction-data'],
    ['/admin/newsletter/composer', 'Marketing', '/admin/newsletter'],
    ['/admin/blogs/composer', 'Marketing', '/admin/blogs'],
    ['/admin/cappe-creators', 'Customers', '/admin/cappe-creators'],
    ['/admin/features', 'Platform', '/admin/features'],
  ])('selects the owning page for %s', (pathname, areaLabel, to) => {
    const active = findAdminPage(pathname)
    expect(active?.area.label).toBe(areaLabel)
    expect(active?.page.to).toBe(to)
    const sidebarItem = adminSidebarItems().find((item) => item.label === areaLabel)
    expect(sidebarItem?.to).toBe(active?.area.to)
    expect(sidebarItem?.activePaths).toContain(to)
  })

  it('links each category to its directory instead of choosing a child tool', () => {
    expect(adminSidebarItems().map((item) => item.to)).toEqual([
      '/admin/areas/customers', '/admin/areas/products-sales', '/admin/areas/compliance',
      '/admin/areas/marketing', '/admin/areas/monitoring', '/admin/areas/platform', '/admin/updates',
    ])
  })

  it.each(['/admin', '/app/settings', '/admin/companies-unknown', '/admin/newsletters'])('does not match a partial or unrelated path: %s', (pathname) => {
    expect(findAdminPage(pathname)).toBeUndefined()
  })
})
