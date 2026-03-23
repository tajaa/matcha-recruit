# ER Copilot — Missing Features Plan

## Context

All backend endpoints already exist. This is purely frontend work adding 4 new tabs and an export sidebar section.

**Backend endpoints ready:**
- `POST/GET /er/cases/{id}/analysis/discrepancies` — Celery async + polling
- `POST/GET /er/cases/{id}/analysis/similar-cases` — SSE streaming
- `POST /er/cases/{id}/search` — sync evidence search
- `POST /er/cases/{id}/guidance/outcomes/stream` — SSE streaming outcome analysis
- `POST /er/cases/{id}/export` — PDF download
- `POST /er/cases/{id}/export/share` + `GET/DELETE` links — shareable S3 links

---

## Files

| Action | File |
|--------|------|
| Modify | `client/src/types/er.ts` |
| Create | `client/src/components/er/ERDiscrepanciesPanel.tsx` |
| Create | `client/src/components/er/ERSimilarCasesPanel.tsx` |
| Create | `client/src/components/er/EREvidenceSearch.tsx` |
| Create | `client/src/components/er/EROutcomePanel.tsx` |
| Modify | `client/src/pages/app/ERCaseDetail.tsx` |

---

## 1. `types/er.ts` — Add missing types

```typescript
// Discrepancies
export interface DiscrepancyItem {
  subject: string
  statement_a: string
  statement_b: string
  severity: 'high' | 'medium' | 'low'
  source_a: string
  source_b: string
  notes?: string
}
export interface CredibilityNote { witness: string; note: string; factors: string[] }
export interface DiscrepancyAnalysis { discrepancies: DiscrepancyItem[]; credibility_notes: CredibilityNote[]; summary: string }
export interface DiscrepancyAnalysisResponse { analysis: DiscrepancyAnalysis; source_documents: string[]; generated_at: string | null }

// Similar Cases
export interface SimilarCaseMatch {
  case_id: string; case_number: string; title: string
  category: ERCaseCategory | null; outcome: ERCaseOutcome | null; status: ERCaseStatus
  created_at: string; closed_at: string | null; resolution_days: number | null
  outcome_effective: boolean | null; similarity_score: number
  score_breakdown: { category_match: number; outcome_relevance: number; status_maturity: number; evidence_profile: number; temporal_recency: number; intake_context_overlap: number; text_similarity: number; investigation_pattern_similarity: number }
  common_factors: string[]; relevance_note: string | null
}
export interface SimilarCasesAnalysis { matches: SimilarCaseMatch[]; pattern_summary: string | null; outcome_distribution: Record<string, number>; generated_at: string; from_cache: boolean; cache_reason: string | null }

// Evidence Search
export interface EvidenceSearchResult { chunk_id: string; content: string; speaker: string | null; source_file: string; document_type: ERDocumentType; page_number: number | null; line_range: string | null; similarity: number; metadata: Record<string, unknown> | null }
export interface EvidenceSearchResponse { results: EvidenceSearchResult[]; query: string; total_chunks: number }

// Outcome Analysis
export interface OutcomeOption { determination: 'substantiated' | 'unsubstantiated' | 'inconclusive'; recommended_action: ERCaseOutcome; action_label: string; reasoning: string; policy_basis: string; hr_considerations: string; precedent_note: string; confidence: 'high' | 'medium' | 'low' }
export interface OutcomeAnalysisResponse { outcomes: OutcomeOption[]; case_summary: string; generated_at: string; model: string }

// Export
export interface ShareLink { id: string; token: string; created_at: string; expires_at: string | null; revoked_at: string | null; download_count: number; last_downloaded_at: string | null; filename: string }
```

---

## 2. `ERDiscrepanciesPanel.tsx`

Pattern: same as `ERTimelinePanel.tsx` (Celery polling, 30 attempts, 2s interval).

- Mount: `GET /er/cases/{id}/analysis/discrepancies` → load cache
- Generate: `POST` → if `status='queued'` poll GET every 2s until result appears
- Empty state: "Detect Discrepancies" button (note: requires ≥2 completed docs)
- Results:
  - Summary paragraph at top
  - Discrepancy cards: subject heading, side-by-side columns (Statement A / Statement B), source labels below each, severity badge (high=red, medium=amber, low=gray)
  - Credibility notes section: witness name + note + factor chips
- Regenerate button

---

## 3. `ERSimilarCasesPanel.tsx`

Pattern: SSE streaming via `fetch` + `ReadableStream`.

- Mount: `GET /er/cases/{id}/analysis/similar-cases` → load cache; if `from_cache=true` show cache badge
- Generate: `POST /er/cases/{id}/analysis/similar-cases` (SSE stream)
  - Parse `data:` lines, handle `type: phase` (show progress message), `type: complete` (set result), `[DONE]` (stop)
- Results:
  - Pattern summary block at top
  - Outcome distribution: simple horizontal bars (CSS width = count/total * 100%)
  - Case match cards: case_number, title, category+outcome badges, similarity score as percentage, resolution_days if closed, common_factors as chips, relevance_note
  - Cache indicator: "From cache · {date}" when from_cache
- Refresh button (sends `?refresh=true` on POST)

---

## 4. `EREvidenceSearch.tsx`

Pattern: sync controlled search.

- Input + "Search" button (also triggers on Enter)
- `top_k` selector: 5 / 10 / 20 (default 5)
- `POST /er/cases/{id}/search` body `{ query, top_k }` → sync, returns immediately
- Results:
  - Header: "X results for '{query}'"
  - Cards: content text, speaker badge (if present), source_file badge, document_type badge, similarity bar (width = similarity * 100%, color = green→amber→red), page/line reference if present
- Empty/no-results states

---

## 5. `EROutcomePanel.tsx`

Pattern: SSE streaming via `fetch` + `ReadableStream`.

- Mount: no auto-load (expensive, user-initiated only)
- Generate: `POST /er/cases/{id}/guidance/outcomes/stream` SSE
  - Parse phase messages → show progress
  - On `type: complete` → set result
- Results:
  - case_summary block at top
  - Outcome option cards (2-3):
    - Determination badge: substantiated=red, unsubstantiated=green, inconclusive=amber
    - Recommended action label + confidence badge
    - Expandable sections: Reasoning / Policy Basis / HR Considerations
    - Precedent note (italicized)
    - "Apply This Outcome" button → `PUT /er/cases/{id}` with `{ outcome: recommended_action, status: 'pending_determination' }` then call `refetch`
- Regenerate button

---

## 6. `ERCaseDetail.tsx` changes

### New tabs (9 total, scrollable tab bar with `overflow-x-auto`):
```
Notes | Documents | Guidance | Discrepancies | Similar Cases | Evidence | Outcome | Policy | Timeline
```

### Sidebar export section (collapsible, below description):
- Chevron toggle to expand/expand "Export Case"
- On expand: `GET /er/cases/{id}/export/links` to load existing links
- **Direct download**: password input + "Download PDF" button
  - Use `fetch` directly (not `api.download`): POST with body `{ password }`, read as blob, trigger download
- **Share link**: password input + expiry dropdown (7 days / 30 days / 90 days / No expiry) + "Create Link"
  - `POST /er/cases/{id}/export/share` body `{ password, expires_in_days }` → show returned URL
- **Links list**: filename, created date, download count, "Revoke" (×) → `DELETE /er/cases/{id}/export/links/{id}` then reload

---

## Verification

1. Open an ER case with ≥2 completed documents
2. **Discrepancies**: click "Detect Discrepancies" → spinner/polling → statement A/B cards, severity badges
3. **Similar Cases**: click "Find Similar Cases" → phase messages → case match cards with similarity %
4. **Evidence**: search a keyword → result cards with similarity bars
5. **Outcome**: click "Generate" → phase messages → outcome cards; "Apply" updates case status
6. **Export sidebar**: expand → enter password → download PDF; create share link → link appears in list; revoke removes it
