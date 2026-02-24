import { useState, useMemo } from 'react';
import type { JurisdictionOption } from '../../api/compliance';

const US_STATES = [
  { value: 'AL', label: 'Alabama' }, { value: 'AK', label: 'Alaska' },
  { value: 'AZ', label: 'Arizona' }, { value: 'AR', label: 'Arkansas' },
  { value: 'CA', label: 'California' }, { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' }, { value: 'DE', label: 'Delaware' },
  { value: 'FL', label: 'Florida' }, { value: 'GA', label: 'Georgia' },
  { value: 'HI', label: 'Hawaii' }, { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' }, { value: 'IN', label: 'Indiana' },
  { value: 'IA', label: 'Iowa' }, { value: 'KS', label: 'Kansas' },
  { value: 'KY', label: 'Kentucky' }, { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' }, { value: 'MD', label: 'Maryland' },
  { value: 'MA', label: 'Massachusetts' }, { value: 'MI', label: 'Michigan' },
  { value: 'MN', label: 'Minnesota' }, { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' }, { value: 'MT', label: 'Montana' },
  { value: 'NE', label: 'Nebraska' }, { value: 'NV', label: 'Nevada' },
  { value: 'NH', label: 'New Hampshire' }, { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' }, { value: 'NY', label: 'New York' },
  { value: 'NC', label: 'North Carolina' }, { value: 'ND', label: 'North Dakota' },
  { value: 'OH', label: 'Ohio' }, { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' }, { value: 'PA', label: 'Pennsylvania' },
  { value: 'RI', label: 'Rhode Island' }, { value: 'SC', label: 'South Carolina' },
  { value: 'SD', label: 'South Dakota' }, { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' }, { value: 'UT', label: 'Utah' },
  { value: 'VT', label: 'Vermont' }, { value: 'VA', label: 'Virginia' },
  { value: 'WA', label: 'Washington' }, { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' },
  { value: 'DC', label: 'Washington D.C.' }
];

export function useJurisdictionSearch(jurisdictions: JurisdictionOption[] | undefined) {
  const [jurisdictionSearch, setJurisdictionSearch] = useState('');

  const jurisdictionsByState = useMemo(() => {
    if (!jurisdictions) return {};
    const grouped: Record<string, JurisdictionOption[]> = {};
    for (const j of jurisdictions) {
      if (!grouped[j.state]) grouped[j.state] = [];
      grouped[j.state].push(j);
    }
    return grouped;
  }, [jurisdictions]);

  const filteredJurisdictions = useMemo(() => {
    if (!jurisdictions) return {};
    const search = jurisdictionSearch.toLowerCase().trim();
    if (!search) return jurisdictionsByState;
    const filtered: Record<string, JurisdictionOption[]> = {};
    for (const [state, items] of Object.entries(jurisdictionsByState)) {
      const stateLabel = US_STATES.find(s => s.value === state)?.label || state;
      const matches = items.filter(j =>
        j.city.toLowerCase().includes(search) ||
        state.toLowerCase().includes(search) ||
        stateLabel.toLowerCase().includes(search)
      );
      if (matches.length > 0) filtered[state] = matches;
    }
    return filtered;
  }, [jurisdictions, jurisdictionSearch, jurisdictionsByState]);

  return {
    jurisdictionSearch,
    setJurisdictionSearch,
    jurisdictionsByState,
    filteredJurisdictions,
  };
}
