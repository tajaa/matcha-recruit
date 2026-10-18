import { describe, it, expect } from 'vitest'
import { buildCodifiedSchema, sectionCode } from './codifiedSchema'
import type { BreakdownRow } from './types'

function row(p: Partial<BreakdownRow>): BreakdownRow {
  return {
    jurisdiction_id: 'j-ca',
    level: 'state',
    country_code: 'US',
    state: 'CA',
    jurisdiction_name: 'California',
    category: 'minimum_wage',
    group: 'labor',
    category_name: 'Minimum wage',
    total: 1,
    codified: 0,
    ...p,
  }
}

const FED = { jurisdiction_id: 'j-fed', level: 'federal', country_code: 'US', state: 'US', jurisdiction_name: 'Federal' }
const MX = { jurisdiction_id: 'j-mx', level: 'national', country_code: 'MX', state: null, jurisdiction_name: 'Mexico' }

describe('sectionCode', () => {
  it('keeps a foreign national jurisdiction out of US federal', () => {
    // The bug this exists for: `national` in this catalog is a FOREIGN country
    // (MX/GB/FR/SG = 119 rows), while US federal law is `federal`. Folding the
    // two — which the tenant-side lens does safely, because every row it sees
    // is American — files Mexican labor law under "Federal" and takes the US
    // federal denominator from 175 to 294.
    expect(sectionCode(row(MX))).toBe('MX')
    expect(sectionCode(row(FED))).toBe('US')
  })

  it('files a US state by its code', () => {
    expect(sectionCode(row({ level: 'state', state: 'CA' }))).toBe('CA')
    expect(sectionCode(row({ level: 'city', state: 'CA' }))).toBe('CA')
  })

  it('assumes US when country_code is missing', () => {
    // Older rows predate country_code; they are all American.
    expect(sectionCode(row({ country_code: null, state: 'AZ' }))).toBe('AZ')
    expect(sectionCode(row({ ...FED, country_code: null }))).toBe('US')
  })
})

describe('buildCodifiedSchema', () => {
  it('pins federal above everything else', () => {
    const s = buildCodifiedSchema([
      row({ level: 'state', state: 'CA' }),
      row(FED),
      row({ jurisdiction_id: 'j-az', level: 'state', state: 'AZ', jurisdiction_name: 'Arizona' }),
    ])
    // Federal law reaches every business; it is not "just another state".
    expect(s.map((x) => x.code)).toEqual(['US', 'AZ', 'CA'])
  })

  it('gives each foreign country its own section', () => {
    const s = buildCodifiedSchema([
      row({ ...FED, total: 175, codified: 11 }),
      row({ ...MX, total: 56 }),
    ])
    expect(s.map((x) => x.code)).toEqual(['US', 'MX'])
    expect(s.find((x) => x.code === 'US')!.total).toBe(175)
    expect(s.find((x) => x.code === 'MX')!.label).toBe('Mexico')
  })

  it('nests a state\'s counties and cities under it, in the order law stacks', () => {
    const s = buildCodifiedSchema([
      row({ jurisdiction_id: 'j-la-city', level: 'city', jurisdiction_name: 'los angeles, CA' }),
      row(FED),
      row({ level: 'state' }),
      row({ jurisdiction_id: 'j-la-cty', level: 'county', jurisdiction_name: 'Los Angeles, CA' }),
    ])
    const ca = s.find((x) => x.code === 'CA')!
    expect(ca.nodes.map((n) => n.level)).toEqual(['state', 'county', 'city'])
    expect(ca.total).toBe(3)
  })

  it('labels places the way the tenant tab does', () => {
    const s = buildCodifiedSchema([
      row({ jurisdiction_id: 'j-la-city', level: 'city', jurisdiction_name: 'los angeles, CA' }),
      row({ jurisdiction_id: 'j-la-cty', level: 'county', jurisdiction_name: 'Los Angeles, CA' }),
    ])
    const labels = s[0].nodes.map((n) => n.label)
    // Same display_name corruption the tenant tab handles: the city is stored
    // lowercase, and the county is named identically to the city it contains.
    expect(labels).toContain('Los Angeles')
    expect(labels).toContain('Los Angeles County')
  })

  it('does not double-suffix a county that already says County', () => {
    const s = buildCodifiedSchema([
      row({ jurisdiction_id: 'j-cook', level: 'county', state: 'IL', jurisdiction_name: 'Cook County, IL' }),
    ])
    expect(s[0].nodes[0].label).toBe('Cook County')
  })

  it('rolls counts up from category to group to node to section', () => {
    const s = buildCodifiedSchema([
      row({ category: 'minimum_wage', total: 10, codified: 2 }),
      row({ category: 'overtime', category_name: 'Overtime', total: 5, codified: 1 }),
      row({ category: 'hipaa_privacy', group: 'healthcare', category_name: 'HIPAA', total: 3, codified: 0 }),
    ])
    const ca = s[0]
    expect({ total: ca.total, codified: ca.codified }).toEqual({ total: 18, codified: 3 })
    const labor = ca.nodes[0].groups.find((g) => g.group === 'labor')!
    expect({ total: labor.total, codified: labor.codified }).toEqual({ total: 15, codified: 3 })
    expect(labor.categories.map((c) => c.category)).toEqual(['minimum_wage', 'overtime'])
  })

  it('merges a category that arrives in more than one cell', () => {
    // Live: federal `overtime` arrives as several cells; unmerged it renders
    // twice, each half looking smaller than the thing actually is.
    const s = buildCodifiedSchema([
      row({ category: 'minimum_wage', total: 4, codified: 1 }),
      row({ category: 'minimum_wage', total: 6, codified: 2 }),
    ])
    const cats = s[0].nodes[0].groups[0].categories
    expect(cats).toHaveLength(1)
    expect(cats[0]).toMatchObject({ total: 10, codified: 3 })
  })

  it('sorts the biggest body of law first', () => {
    const s = buildCodifiedSchema([
      row({ group: 'healthcare', category: 'hipaa_privacy', total: 50, codified: 0 }),
      row({ group: 'labor', total: 10, codified: 0 }),
    ])
    expect(s[0].nodes[0].groups.map((g) => g.group)).toEqual(['healthcare', 'labor'])
  })

  it('buckets an unknown category rather than dropping it', () => {
    // The category set is discovered at runtime (vertical_coverage writes new
    // ones), so a row can carry a category compliance_categories doesn't know.
    // Dropping it would make the tab's totals disagree with the corpus.
    const s = buildCodifiedSchema([row({ group: '', category_name: '', category: 'brand_new', total: 7, codified: 1 })])
    expect(s[0].total).toBe(7)
    const g = s[0].nodes[0].groups[0]
    expect(g.group).toBe('other')
    expect(g.categories[0].name).toBe('brand_new')
  })

  it('totals reconcile with the payload', () => {
    const rows = [
      row({ ...FED, total: 147, codified: 10 }),
      row({ level: 'state', total: 694, codified: 14 }),
      row({ jurisdiction_id: 'j-la-city', level: 'city', jurisdiction_name: 'los angeles, CA', total: 140, codified: 1 }),
      row({ jurisdiction_id: 'j-la-cty', level: 'county', jurisdiction_name: 'Los Angeles, CA', total: 97, codified: 1 }),
      row({ ...MX, total: 56, codified: 0 }),
    ]
    const s = buildCodifiedSchema(rows)
    const sum = (k: 'total' | 'codified') => s.reduce((n, x) => n + x[k], 0)
    expect(sum('total')).toBe(rows.reduce((n, r) => n + r.total, 0))
    expect(sum('codified')).toBe(rows.reduce((n, r) => n + r.codified, 0))
  })

  it('returns nothing for an empty corpus rather than throwing', () => {
    expect(buildCodifiedSchema([])).toEqual([])
  })
})
