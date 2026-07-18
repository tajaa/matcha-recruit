import type { Finding } from '../auditRules'

export const STATES_50: { slug: string; name: string }[] = [
  ['alabama', 'Alabama'], ['alaska', 'Alaska'], ['arizona', 'Arizona'], ['arkansas', 'Arkansas'],
  ['california', 'California'], ['colorado', 'Colorado'], ['connecticut', 'Connecticut'],
  ['delaware', 'Delaware'], ['district-of-columbia', 'District of Columbia'], ['florida', 'Florida'],
  ['georgia', 'Georgia'], ['hawaii', 'Hawaii'], ['idaho', 'Idaho'], ['illinois', 'Illinois'],
  ['indiana', 'Indiana'], ['iowa', 'Iowa'], ['kansas', 'Kansas'], ['kentucky', 'Kentucky'],
  ['louisiana', 'Louisiana'], ['maine', 'Maine'], ['maryland', 'Maryland'], ['massachusetts', 'Massachusetts'],
  ['michigan', 'Michigan'], ['minnesota', 'Minnesota'], ['mississippi', 'Mississippi'],
  ['missouri', 'Missouri'], ['montana', 'Montana'], ['nebraska', 'Nebraska'], ['nevada', 'Nevada'],
  ['new-hampshire', 'New Hampshire'], ['new-jersey', 'New Jersey'], ['new-mexico', 'New Mexico'],
  ['new-york', 'New York'], ['north-carolina', 'North Carolina'], ['north-dakota', 'North Dakota'],
  ['ohio', 'Ohio'], ['oklahoma', 'Oklahoma'], ['oregon', 'Oregon'], ['pennsylvania', 'Pennsylvania'],
  ['rhode-island', 'Rhode Island'], ['south-carolina', 'South Carolina'], ['south-dakota', 'South Dakota'],
  ['tennessee', 'Tennessee'], ['texas', 'Texas'], ['utah', 'Utah'], ['vermont', 'Vermont'],
  ['virginia', 'Virginia'], ['washington', 'Washington'], ['west-virginia', 'West Virginia'],
  ['wisconsin', 'Wisconsin'], ['wyoming', 'Wyoming'],
].map(([slug, name]) => ({ slug, name }))

export const SEVERITY_BG: Record<Finding['severity'], string> = {
  high: 'rgba(193, 84, 58, 0.08)',
  medium: 'rgba(193, 159, 58, 0.08)',
  low: 'rgba(90, 140, 90, 0.08)',
}
export const SEVERITY_COLOR: Record<Finding['severity'], string> = {
  high: '#c1543a',
  medium: '#c19f3a',
  low: '#5a8c5a',
}
