import type {
  ContactInput, ProspectStatus, SalesCampaign, SalesProspect, SalesSegment, SalesService,
} from '../../api/matchaWork/sales'

/** A batch a person can read every message of before approving (server `MAX_BATCH`). */
export const MAX_BATCH = 50
export const MAX_IMPORT = 1000
/** The server's footer placeholder: a campaign can't send until it is replaced. */
export const FOOTER_PLACEHOLDER = '[Your business name and postal address]'

export class ImportError extends Error {}

/** Normalized header (lowercase letters and digits only) -> field. The same
 *  list as the Mac Pipeline (`SalesModels.swift`), so a CSV imports alike. */
const ALIASES: Record<string, string> = {
  email: 'email', emailaddress: 'email', workemail: 'email', businessemail: 'email', contactemail: 'email',
  name: 'name', fullname: 'name', contactname: 'name', contact: 'name',
  firstname: 'first', givenname: 'first',
  lastname: 'last', surname: 'last', familyname: 'last',
  company: 'company', companyname: 'company', organization: 'company', organisation: 'company',
  business: 'company', account: 'company', accountname: 'company',
  website: 'website', websiteurl: 'website', url: 'website', domain: 'website', companywebsite: 'website', web: 'website',
  notes: 'notes', note: 'notes', description: 'notes',
}

const fieldFor = (header: string) => ALIASES[header.toLowerCase().replace(/[^a-z0-9]/g, '')]
const EMAIL = /^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/

/** CSV/TSV with a header row, or one email per line. Quoted fields, escaped
 *  quotes, multiline notes, BOM and CRLF are read; a malformed row rejects
 *  the whole import with the row it was on. */
export function parseContacts(input: string): ContactInput[] {
  if (new TextEncoder().encode(input).length > 1_000_000) throw new ImportError('Import at most 1 MB at a time.')
  const text = input.replace(/\r\n?/g, '\n').replace(/^\uFEFF/, '')
  const delimiter = text.split('\n', 1)[0].includes('\t') ? '\t' : ','
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  let afterQuote = false
  const endRow = () => {
    row.push(field.trim())
    if (row.some((v) => v)) rows.push(row)
    row = []
    field = ''
    afterQuote = false
  }
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; continue }
        quoted = false
        afterQuote = true
      } else field += c
    } else if (c === delimiter) {
      row.push(field.trim())
      field = ''
      afterQuote = false
    } else if (c === '\n') {
      endRow()
    } else if (c === '"') {
      if (field || afterQuote) throw new ImportError(`Unexpected quote on row ${rows.length + 1}.`)
      quoted = true
    } else {
      if (afterQuote && !/\s/.test(c)) throw new ImportError(`Unexpected text after a quote on row ${rows.length + 1}.`)
      field += c
    }
  }
  if (quoted) throw new ImportError('An import field has an unclosed quote.')
  endRow()
  const first = rows[0]
  if (!first) throw new ImportError('Paste email addresses or a CSV with an email, name, company or website column.')
  const mapped = first.map(fieldFor)
  const hasHeader = mapped.some(Boolean)
  if (hasHeader) {
    const known = mapped.filter(Boolean)
    if (new Set(known).size !== known.length) {
      throw new ImportError('Each of email, name, company, website and notes can appear in only one column.')
    }
    if (known.includes('name') && (known.includes('first') || known.includes('last'))) {
      throw new ImportError('Use either a full-name column or first/last name columns, not both.')
    }
  }
  const data = hasHeader ? rows.slice(1) : rows
  if (!data.length || data.length > MAX_IMPORT) throw new ImportError('Import between 1 and 1,000 prospects.')
  return data.map((values, offset) => {
    const line = offset + (hasHeader ? 2 : 1)
    if (values.length !== (hasHeader ? first.length : 1)) {
      throw new ImportError(`Row ${line} has the wrong number of fields. Use a header row for CSV contacts.`)
    }
    const fields: Record<string, string> = {}
    if (hasHeader) mapped.forEach((key, i) => { if (key) fields[key] = values[i] })
    else fields.email = values[0]
    const email = (fields.email ?? '').toLowerCase()
    if (email && (email.length > 254 || !EMAIL.test(email))) throw new ImportError(`Row ${line} needs one complete email address.`)
    const name = fields.name ?? [fields.first, fields.last].filter(Boolean).join(' ')
    const company = fields.company ?? ''
    const notes = fields.notes ?? ''
    let website = fields.website ?? ''
    if (website && !website.includes('://')) website = `https://${website}`
    if (website) {
      let ok = false
      try {
        const url = new URL(website)
        ok = (url.protocol === 'http:' || url.protocol === 'https:') && !!url.hostname && !url.username && !url.password
      } catch { ok = false }
      if (!ok) throw new ImportError(`Row ${line} has an invalid website.`)
    }
    if (name.length > 200 || company.length > 200 || notes.length > 4000 || website.length > 2000) {
      throw new ImportError(`Row ${line} has a field that is too long.`)
    }
    if (!email && !name && !company && !website) throw new ImportError(`Row ${line} needs a contact or business.`)
    return { email, name, company, website, notes }
  })
}

/** Ready to approve: a draft with an address, subject and body. */
export function sendable(p: SalesProspect): boolean {
  return p.status === 'draft' && !!p.email && !!p.subject && !!p.body
}

const STATUS_ORDER: Record<ProspectStatus, number> = {
  unknown: 0, failed: 1, draft: 2, prospect: 3, approved: 4, claimed: 5, sent: 6, opted_out: 7,
}

/** What needs the person first: unconfirmed and failed messages, then drafts
 *  and leads. In a consulting campaign the best fit comes first within each. */
export function orderProspects(prospects: SalesProspect[], consulting: boolean): SalesProspect[] {
  return [...prospects].sort((a, b) =>
    STATUS_ORDER[a.status] - STATUS_ORDER[b.status]
    || (consulting ? (b.fit ?? 0) - (a.fit ?? 0) : 0))
}

export function footerProblem(footer: string): string | null {
  const text = footer.trim()
  if (!text || text.includes(FOOTER_PLACEHOLDER)) {
    return "Add a footer with how to opt out and your business's postal address before sending."
  }
  return null
}

/** Exactly what is sent: the reviewed body, then the reviewed footer (server `compose_body`). */
export function composeBody(body: string, footer: string): string {
  const end = footer.trim()
  return end ? `${body.trimEnd()}\n\n${end}` : body
}

export const STATUS_LABEL: Record<ProspectStatus, string> = {
  prospect: 'Lead', draft: 'Draft', approved: 'Approved', claimed: 'Sending', sent: 'Sent',
  failed: 'Failed', unknown: 'Unconfirmed', opted_out: 'Do not contact',
}

export const SEGMENT_LABEL: Record<Exclude<SalesSegment, ''>, string> = {
  growing: 'Growing, no HR lead', regulated: 'Healthcare & manufacturing', ai: 'Adopting AI', hourly: 'Restaurants & retail',
}

export const SERVICE_LABEL: Record<Exclude<SalesService, ''>, string> = {
  hr: 'HR consulting', grc: 'Governance, risk & compliance', er: 'Employee relations', ai: 'AI integration review',
}

export const FIT_LABEL: Record<number, string> = { 3: 'Strong fit', 2: 'Good fit', 1: 'Weak fit' }

/** The ask a person finishes and sends to Espresso to research and draft. */
export function assistantPrompt(campaign: SalesCampaign): string {
  const consulting = campaign.playbook === 'consulting'
  return [
    `Work on my sales campaign ${campaign.id} in workspace ${campaign.project_id}.`,
    'Read the saved campaign, target, offer and prospects first.',
    consulting
      ? 'It is a consulting campaign: find businesses in its segments with a current public signal, save each one\'s segment, service, signal and fit with sources, and draft for the best fits first.'
      : 'Discover prospects matching my target if needed, research them using public source links, and save personalized email drafts.',
    'Work in batches and report how many remain. I will review and send in Sales.',
    '',
    'My instructions: ',
  ].join('\n')
}
