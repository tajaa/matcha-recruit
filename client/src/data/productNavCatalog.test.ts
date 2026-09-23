import { describe, expect, it } from 'vitest'
import { buildProductNav, withCompanyAddons } from './productNavCatalog'
import type { ProductDefinition } from '../types/dashboard'

const product = { features: ['employees', 'employee_schedule'], nav: null } as unknown as ProductDefinition
const labels = (entries: { label: string }[]) => entries.map((e) => e.label)

describe('withCompanyAddons', () => {
  it('adds a company-enabled add-on the product does not grant, before Company', () => {
    const out = withCompanyAddons(buildProductNav(product), (f) => f === 'symlink')
    expect(labels(out)).toEqual(['Employees', 'Schedule', 'Sym-links', 'Company'])
  })

  it('leaves the nav alone without the flag', () => {
    const base = buildProductNav(product)
    expect(withCompanyAddons(base, () => false)).toBe(base)
  })

  it('never pulls in default-on flags that are not add-ons', () => {
    const out = withCompanyAddons(buildProductNav(product), () => true)
    expect(labels(out)).not.toContain('Handbooks')
    expect(labels(out).filter((l) => l === 'Sym-links')).toHaveLength(1)
  })

  it('does not duplicate an add-on the product already grants', () => {
    const granted = { features: ['symlink'], nav: null } as unknown as ProductDefinition
    const out = withCompanyAddons(buildProductNav(granted), () => true)
    expect(labels(out).filter((l) => l === 'Sym-links')).toHaveLength(1)
  })
})
