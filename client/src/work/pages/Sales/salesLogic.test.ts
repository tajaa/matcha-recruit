import { describe, expect, it } from 'vitest'
import {
  FOOTER_PLACEHOLDER, ImportError, assistantPrompt, composeBody, footerProblem, orderProspects, parseContacts, sendable,
} from './salesLogic'
import { campaign, prospect } from './testFixtures'

describe('parseContacts', () => {
  it('reads one email per line', () => {
    expect(parseContacts('Ana@Example.com\n\nbo@example.com\r\n').map((c) => c.email))
      .toEqual(['ana@example.com', 'bo@example.com'])
  })

  it('reads a CSV by its headers, with CRM spellings, quotes and multiline notes', () => {
    const csv = '﻿Email Address,First Name,Last Name,Company Name,Website URL,Notes,Phone\n'
      + 'ana@example.com,Ana,Ruiz,"Acme, Inc.",acme.example,"Met at ""the"" expo\nfollow up",555\n'
    expect(parseContacts(csv)).toEqual([{
      email: 'ana@example.com', name: 'Ana Ruiz', company: 'Acme, Inc.', website: 'https://acme.example',
      notes: 'Met at "the" expo\nfollow up',
    }])
  })

  it('reads a TSV and leads without an email', () => {
    expect(parseContacts('company\twebsite\nAcme\thttps://acme.example')[0])
      .toMatchObject({ email: '', company: 'Acme', website: 'https://acme.example' })
  })

  it.each([
    ['', 'Paste email addresses'],
    ['not an email', 'Row 1 needs one complete email address.'],
    ['email,email\na@example.com,b@example.com', 'only one column'],
    ['name,first name\nAna,Ana', 'either a full-name column'],
    ['email,name\na@example.com', 'Row 2 has the wrong number of fields'],
    ['email\n"a@example.com', 'unclosed quote'],
    ['email,website\na@example.com,ftp://x', 'Row 2 has an invalid website.'],
    ['email,company,notes\n,,met at expo', 'Row 2 needs a contact or business.'],
  ])('rejects %j', (input, message) => {
    expect(() => parseContacts(input)).toThrow(ImportError)
    expect(() => parseContacts(input)).toThrow(message)
  })

  it('takes at most 1,000 at a time', () => {
    const many = Array.from({ length: 1001 }, (_, i) => `p${i}@example.com`).join('\n')
    expect(() => parseContacts(many)).toThrow('between 1 and 1,000')
  })
})

describe('the campaign rules', () => {
  it('only a complete draft can be sent', () => {
    expect(sendable(prospect())).toBe(true)
    expect(sendable(prospect({ email: '' }))).toBe(false)
    expect(sendable(prospect({ body: '' }))).toBe(false)
    expect(sendable(prospect({ status: 'sent' }))).toBe(false)
  })

  it('puts what needs the person first, and the best fit first in consulting', () => {
    const list = [
      prospect({ id: 'sent', status: 'sent' }),
      prospect({ id: 'weak', fit: 1 }),
      prospect({ id: 'strong', fit: 3 }),
      prospect({ id: 'unknown', status: 'unknown' }),
    ]
    expect(orderProspects(list, true).map((p) => p.id)).toEqual(['unknown', 'strong', 'weak', 'sent'])
    expect(orderProspects(list, false).map((p) => p.id)).toEqual(['unknown', 'weak', 'strong', 'sent'])
  })

  it('needs a real footer, and sends the body then the footer', () => {
    expect(footerProblem('')).toBeTruthy()
    expect(footerProblem(`Reply stop.\n${FOOTER_PLACEHOLDER}`)).toBeTruthy()
    expect(footerProblem('Reply stop.\nAcme, 1 Main St')).toBeNull()
    expect(composeBody('Hello  \n', ' Reply stop. ')).toBe('Hello\n\nReply stop.')
    expect(composeBody('Hello', '')).toBe('Hello')
  })

  it('asks Espresso to work the campaign, the consulting way when it is one', () => {
    expect(assistantPrompt(campaign())).toContain('Work on my sales campaign c1 in workspace w1')
    expect(assistantPrompt(campaign({ playbook: 'consulting' }))).toContain('signal and fit')
  })
})
