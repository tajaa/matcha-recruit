import { describe, expect, it } from 'vitest'
import { parseEmployeesCsv, parseLocationsCsv } from './csv'

describe('S&C onboarding CSV parsing', () => {
  it('parses quoted location fields and CRLF rows', () => {
    expect(parseLocationsCsv('name,address,city,state,zipcode\r\nHQ,"1 Main, Suite 2",Austin,TX,78701')).toEqual([
      { name: 'HQ', address: '1 Main, Suite 2', city: 'Austin', state: 'TX', zipcode: '78701' },
    ])
  })

  it('reports the required employee header', () => {
    expect(() => parseEmployeesCsv('email,first_name\na@example.com,A')).toThrow(
      'Expected header: email,first_name,last_name,work_state,job_title,department',
    )
  })

  it('reports incomplete rows with their source line', () => {
    expect(() => parseLocationsCsv('name,address,city,state,zipcode\nHQ,1 Main,,TX,78701')).toThrow(
      'Row 2 must contain all 5 values',
    )
  })

  it('does not treat a header-only file as an intentional skip', () => {
    expect(() => parseEmployeesCsv('email,first_name,last_name,work_state,job_title,department\n')).toThrow(
      'CSV must contain at least one data row',
    )
  })

  it('reports an unclosed quoted value', () => {
    expect(() => parseLocationsCsv('name,address,city,state,zipcode\nHQ,"1 Main,Austin,TX,78701')).toThrow(
      'CSV contains an unclosed quoted value',
    )
  })

  it('reports field validation with the source row', () => {
    expect(() => parseLocationsCsv('name,address,city,state,zipcode\nHQ,1 Main,Austin,Texas,78701')).toThrow(
      'Row 2 state must use a two-letter code',
    )
    expect(() => parseEmployeesCsv('email,first_name,last_name,work_state,job_title,department\nnot-email,A,One,TX,Cook,Kitchen')).toThrow(
      'Row 2 email is invalid',
    )
  })

  it('rejects duplicate import keys', () => {
    expect(() => parseEmployeesCsv('email,first_name,last_name,work_state,job_title,department\na@example.com,A,One,TX,Cook,Kitchen\nA@example.com,A,Two,TX,Cook,Kitchen')).toThrow(
      'Row 3 duplicates an earlier employee email',
    )
    expect(() => parseLocationsCsv('name,address,city,state,zipcode\nHQ,1 Main,Austin,TX,78701\n hq ,1 MAIN,austin,tx,78701')).toThrow(
      'Row 3 duplicates an earlier location row',
    )
  })
})
