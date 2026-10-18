import { api } from '../client'
import type { SalesSetupStatus } from '../../types/scheduleSales'

export const fetchSalesSetup = (locationId: string) =>
  api.get<SalesSetupStatus>(`/inventory/sales/setup?${new URLSearchParams({ location_id: locationId })}`)

export const registerSalesSender = (locationId: string, fromAddress: string, subjectMatch: string) =>
  api.post('/inventory/sales/sources', {
    location_id: locationId, from_address: fromAddress.trim(), subject_match: subjectMatch.trim() || null,
  })

export const authorizeSalesSquare = () =>
  api.get<{ oauth_url: string }>('/inventory/sales/connections/authorize')
