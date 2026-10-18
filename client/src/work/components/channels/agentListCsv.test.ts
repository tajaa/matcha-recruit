import { describe, expect, it } from 'vitest'
import { csvCell, csvFilename, jobPostingsCsv, placesCsv } from './agentListCsv'

describe('agentListCsv', () => {
  it('quotes what needs quoting and never lets a cell be a formula', () => {
    expect(csvCell('Blue Bottle')).toBe('Blue Bottle')
    expect(csvCell('Cafe, "the" best')).toBe('"Cafe, ""the"" best"')
    expect(csvCell('=HYPERLINK("x")')).toBe(`"'=HYPERLINK(""x"")"`)
    expect(csvCell('+1 213')).toBe("'+1 213")
    expect(csvCell(null)).toBe('')
    expect(csvCell(4.5)).toBe('4.5')
  })

  it('makes a places sheet with every column, blanks where Maps had nothing', () => {
    const csv = placesCsv([
      { id: 'P1', name: 'Cafe 1', category: 'Coffee shop', rating: 4.5, reviews: 101, address: '1 Sunset Blvd, LA', phone: '(213) 555-0001', website: 'https://cafe1.test/', maps_url: 'https://maps.test/p1' },
      { id: 'P2', name: 'Cafe 2' },
    ])
    const [header, first, second] = csv.split('\r\n')
    expect(header).toBe('Name,Category,Rating,Reviews,Price,Address,Phone,Website,Google Maps')
    expect(first).toBe('Cafe 1,Coffee shop,4.5,101,,"1 Sunset Blvd, LA",(213) 555-0001,https://cafe1.test/,https://maps.test/p1')
    expect(second).toBe('Cafe 2,,,,,,,,')
  })

  it('makes a jobs sheet that says which postings were read at the employer', () => {
    const csv = jobPostingsCsv([
      { id: 'J1', title: 'Designer', company: 'Figma', pay: '$180K–$220K', verified: true, at_employer: true, apply_url: 'https://x.test' },
      { id: 'J2', title: 'Designer', company: 'Plug', verified: true, read_on: 'builtin.com' },
      { id: 'J3', title: 'Designer', company: 'Acme' },
    ])
    const [, figma, plug, acme] = csv.split('\r\n')
    expect(figma).toBe('Designer,Figma,,,$180K–$220K,,Live at the employer,https://x.test')
    expect(plug).toBe('Designer,Plug,,,,,Live on builtin.com,')
    expect(acme).toBe('Designer,Acme,,,,,Listed on Google Jobs only,')
  })

  it('names the file after the list', () => {
    expect(csvFilename('Independent coffee shops in LA!', 'places')).toBe('independent-coffee-shops-in-la.csv')
    expect(csvFilename(undefined, 'places')).toBe('places.csv')
  })
})
