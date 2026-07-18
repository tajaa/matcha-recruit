import type { ApproveResult, UncodifiedItem } from '../types'
import type { FitGatedRow } from '../../../../api/admin/adminOnboarding'

/** A withheld row from the fit map → the codify chain's shape.
 *  `catalog_id`, not `id`: codification acts on the catalog row, while `id` is
 *  the per-location projection. Seeding with the latter 404s on a row that
 *  plainly exists. */
export function fromGated(g: FitGatedRow): ApproveResult {
  return {
    id: g.catalog_id, title: g.title ?? '(untitled)',
    // Carried, not nulled: openCodify pre-fills the citation box by scraping
    // these. Nulling them hands the admin an empty box on all 302 rows.
    description: g.description, current_value: g.current_value,
    source_url: g.source_url, source_name: g.source_name, regulation_key: g.regulation_key,
    codified: false, statute_citation: null, citation_url: null, citation_item_id: null,
    state: null, city: null,
  }
}

export function fromUncodified(it: UncodifiedItem): ApproveResult {
  return {
    id: it.id, title: it.title, description: it.description, current_value: it.current_value,
    source_url: it.source_url, source_name: it.source_name, regulation_key: it.regulation_key,
    codified: false, statute_citation: null, citation_url: null, citation_item_id: null,
    state: it.state, city: it.city,
    blocked_companies: it.blocked_companies,
  }
}
