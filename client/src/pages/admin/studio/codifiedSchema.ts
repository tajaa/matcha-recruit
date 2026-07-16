import type { BreakdownRow, AuthorityNode, CategoryStat, GroupStat, SchemaSection } from './types'

// Order the law reaches a business in: the federal floor first, then the state,
// then the local rules that stack on top. Anything unrecognized sorts last
// rather than being dropped — the counts have to reconcile to the corpus.
const LEVEL_RANK: Record<string, number> = { federal: 0, national: 0, state: 1, county: 2, city: 3 }

/**
 * Which section does this authority belong to?
 *
 * NOT the level string. `national` in this catalog is a FOREIGN country (Mexico,
 * the UK, France, Singapore); US federal law is `federal`. The tenant-side lens
 * folds national→federal safely because every row it sees is American — do that
 * here and Mexican labor law lands under "Federal", taking the US denominator
 * from 175 to 294.
 */
export function sectionCode(row: BreakdownRow): string {
  const country = (row.country_code || 'US').toUpperCase()
  if (country !== 'US') return country
  if (row.level === 'federal' || row.level === 'national') return 'US'
  return (row.state || '').toUpperCase() || 'US'
}

function nodeLabel(row: BreakdownRow): string {
  const name = (row.jurisdiction_name || '').trim()
  if (row.level === 'federal') return 'Federal'
  if (row.level === 'national') return name || row.country_code || 'National'
  if (row.level === 'state') return name || row.state || 'Statewide'
  // display_name is authored inconsistently ("los angeles, CA" for the city,
  // "Los Angeles, CA" for the county containing it) — the tenant tab hit the
  // same thing. Strip the trailing state code and re-case the place.
  const place = (name.split(',')[0] || '').trim()
  if (!place) return row.state || 'Unknown'
  const cased = place === place.toLowerCase()
    ? place.replace(/\b\w/g, (c) => c.toUpperCase())
    : place
  if (row.level === 'county' && !/county/i.test(cased)) return `${cased} County`
  return cased
}

function rollUp<T extends { total: number; codified: number }>(items: T[]) {
  return items.reduce(
    (acc, i) => ({ total: acc.total + i.total, codified: acc.codified + i.codified }),
    { total: 0, codified: 0 },
  )
}

/** Group one authority's cells into `group → categories`, biggest domain first. */
function buildGroups(rows: BreakdownRow[]): GroupStat[] {
  const byGroup = new Map<string, BreakdownRow[]>()
  for (const r of rows) {
    const g = r.group || 'other'
    const list = byGroup.get(g)
    if (list) list.push(r)
    else byGroup.set(g, [r])
  }

  const groups: GroupStat[] = []
  for (const [group, groupRows] of byGroup) {
    // Merge repeats: two cells differing only in a column we don't group on
    // would otherwise render the same category twice, each half looking
    // smaller than the thing actually is.
    const byCategory = new Map<string, CategoryStat>()
    for (const r of groupRows) {
      const existing = byCategory.get(r.category)
      if (existing) {
        existing.total += r.total
        existing.codified += r.codified
      } else {
        byCategory.set(r.category, {
          category: r.category,
          name: r.category_name || r.category,
          total: r.total,
          codified: r.codified,
        })
      }
    }
    const categories = [...byCategory.values()].sort(
      (a, b) => b.total - a.total || a.name.localeCompare(b.name),
    )
    groups.push({ group, ...rollUp(categories), categories })
  }
  return groups.sort((a, b) => b.total - a.total || a.group.localeCompare(b.group))
}

/**
 * The corpus as a jurisdictional hierarchy: Federal, then one section per state
 * carrying its statewide authority plus the counties and cities inside it, then
 * any foreign country we hold law for.
 *
 * The point is the denominator. "1773 requirements, 29 codified" is a number
 * nobody can act on. "147 federal labor laws, 10 codified" names a body of law,
 * says how much of it we have proven, and implies the next move.
 */
export function buildCodifiedSchema(rows: BreakdownRow[]): SchemaSection[] {
  // An authority is a jurisdiction row, so that is the node identity — never
  // (level, state), which cannot tell US federal law from Mexico's.
  const byNode = new Map<string, BreakdownRow[]>()
  for (const row of rows) {
    const list = byNode.get(row.jurisdiction_id)
    if (list) list.push(row)
    else byNode.set(row.jurisdiction_id, [row])
  }

  const nodesBySection = new Map<string, AuthorityNode[]>()
  for (const [jurisdictionId, nodeRows] of byNode) {
    const first = nodeRows[0]
    const groups = buildGroups(nodeRows)
    const node: AuthorityNode = {
      id: jurisdictionId,
      level: first.level,
      state: first.state || null,
      label: nodeLabel(first),
      ...rollUp(groups),
      groups,
    }
    const code = sectionCode(first)
    const bucket = nodesBySection.get(code)
    if (bucket) bucket.push(node)
    else nodesBySection.set(code, [node])
  }

  const sections: SchemaSection[] = []
  for (const [code, nodes] of nodesBySection) {
    nodes.sort(
      (a, b) =>
        (LEVEL_RANK[a.level] ?? 9) - (LEVEL_RANK[b.level] ?? 9) ||
        b.total - a.total ||
        a.label.localeCompare(b.label),
    )
    sections.push({
      code,
      // A single-authority section (US federal, or a country) is named by that
      // authority; a state section is named by its code and holds many.
      label: nodes.length === 1 && nodes[0].level !== 'state' ? nodes[0].label : code,
      ...rollUp(nodes),
      nodes,
    })
  }

  // Federal pins to the top: it reaches every business, so it is never "just
  // another state". The rest sort by code so the list stays scannable.
  return sections.sort((a, b) => {
    if (a.code === 'US') return -1
    if (b.code === 'US') return 1
    return a.code.localeCompare(b.code)
  })
}
