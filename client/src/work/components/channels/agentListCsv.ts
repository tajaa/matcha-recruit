import type { AgentJobPosting, AgentPlace } from '../../types'

/**
 * CSV for the lists Espresso finds (places on Google Maps, open job postings),
 * built in the browser from the rows the server sent, so the person can take a
 * list into a spreadsheet or a CRM without copying it out of chat.
 */

/** One cell: quoted when it needs to be, and never read as a formula by a
 *  spreadsheet (a business name can start with "=" or "+"). */
export function csvCell(value: unknown): string {
  let text = value == null ? '' : String(value)
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(header: string[], rows: unknown[][]): string {
  return [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')
}

export function placesCsv(places: AgentPlace[]): string {
  return toCsv(
    ['Name', 'Category', 'Rating', 'Reviews', 'Price', 'Address', 'Phone', 'Website', 'Google Maps'],
    places.map((p) => [p.name, p.category, p.rating, p.reviews, p.price, p.address, p.phone, p.website, p.maps_url]),
  )
}

export function jobPostingsCsv(jobs: AgentJobPosting[]): string {
  return toCsv(
    ['Title', 'Company', 'Location', 'Remote', 'Pay', 'Posted', 'Checked', 'Apply'],
    jobs.map((j) => [
      j.title, j.company, j.location, j.remote ? 'yes' : '', j.pay, j.posted, checkedText(j), j.apply_url,
    ]),
  )
}

/** Whether a posting was found still up, and where. */
export function checkedText(job: AgentJobPosting): string {
  if (job.at_employer) return 'Live at the employer'
  if (job.verified) return `Live on ${job.read_on || 'a job board'}`
  return 'Listed on Google Jobs only'
}

/** "Independent coffee shops in LA" -> independent-coffee-shops-in-la.csv */
export function csvFilename(title: string | undefined, fallback: string): string {
  const slug = (title || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
  return `${slug || fallback}.csv`
}

/** Hands the person a file; the BOM makes Excel read UTF-8 names right. */
export function downloadCsv(csv: string, filename: string): void {
  const url = URL.createObjectURL(new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
