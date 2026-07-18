import type { SetupForm, LocationEntry } from './types'

export const EMPTY_SETUP: SetupForm = {
  company_name: '',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  industry: '',
  company_size: '',
  headcount: '1',
  invite_immediately: true,
  locations: [],
  notes: '',
  specialties: '',
}

export const EMPTY_LOCATION: LocationEntry = { city: '', state: '', type: 'headquarters' }

export const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
  'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
  'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC',
]

export const LOCATION_TYPES = ['headquarters', 'branch', 'remote']
