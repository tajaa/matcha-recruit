import type { SalesCampaign, SalesProspect } from '../../api/matchaWork/sales'

// Shared test rows for the Sales page's tests.

export const prospect = (over: Partial<SalesProspect> = {}): SalesProspect => ({
  id: 'p1', email: 'ana@example.com', name: 'Ana Ruiz', company: 'Acme Dental', website: '', notes: '',
  research: '', sources: [], subject: 'Hi', body: 'Hello', stage: 'lead', status: 'draft', error: null,
  sent_at: null, segment: '', service: '', signal: '', fit: null, review_token: 't1', ...over,
})

export const campaign = (over: Partial<SalesCampaign> = {}): SalesCampaign => ({
  id: 'c1', project_id: 'w1', title: 'Clinics', target: '', offer: '', footer: 'Reply stop.\nAcme, 1 Main St',
  playbook: '', cta_url: '', status: 'idle', sender: null, error: null, updated_at: '2026-10-30T00:00:00Z', ...over,
})
