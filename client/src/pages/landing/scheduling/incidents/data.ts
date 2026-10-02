/** One illustrative case, told from report to signed copy. The stages, labels
 *  and rules are the product's own (HR cases); the café, people and times are
 *  the demo café's, shared with the hero animation. */
export const CASE = {
  number: 'HRC-2026-0001',
  incident: 'IR-2026-10-3F78',
  employee: 'Jonah B.',
  employeeFull: 'Jonah Brooks',
  reporter: 'Ana R.',
} as const

/** The opening threshold: a violated or bent match at or above this opens a
 *  case (the company can change it). */
export const FLAG_THRESHOLD = 60

/** What the handbook check reported. "Related" is shown, never flagged. */
export const MATCHES = [
  { policy: 'Attendance and Punctuality', relevance: 'Violated', confidence: 98, opens: true },
  { policy: 'Corrective Action', relevance: 'Related', confidence: 85, opens: false },
] as const

/** The first seconds after Ana taps Submit. */
export const FIRST_SECONDS = [
  { at: '+0 s', title: 'Filed', body: 'Numbered and saved. Ana can put her phone away.' },
  { at: '', title: 'Sorted', body: 'Type and severity are filled in for her.' },
  { at: '', title: 'Checked', body: 'Read against your handbook and your policies.' },
  { at: '+10 s', title: 'Opened', body: 'A likely violation opens an HR case. Ana and HR get a notice with the numbers and policy names, not the story.' },
] as const

/** Margin notes on the letter, one per review layer. Red pen is something
 *  the manager fixes, amber waits on HR, green is clear. */
export type NoteTone = 'clear' | 'hr' | 'fix'
export const NOTES: { n: number; tone: NoteTone; layer: string; title: string; body: string }[] = [
  {
    n: 1,
    tone: 'clear',
    layer: 'Protected leave',
    title: 'Clear',
    body: 'None of the dates overlap leave the law protects. If they did, this would hold for HR, with no override.',
  },
  {
    n: 2,
    tone: 'hr',
    layer: 'Discipline history',
    title: 'Skips a step',
    body: 'No earlier warning on file in the last 12 months. Noted for HR, not blocked.',
  },
  {
    n: 3,
    tone: 'fix',
    layer: 'Wording',
    title: 'Stick to what happened',
    body: 'A judgment about character, not a fact. Use the dates.',
  },
  {
    n: 4,
    tone: 'fix',
    layer: 'Letter structure',
    title: 'No signature line',
    body: 'The employee needs a place to sign. Ana adds it before HR spends time on it.',
  },
]

/** What the signed-copy check reads off the page. */
export const SIGNED_CHECKS = [
  { k: 'Readable', v: 'Not encrypted, every page there' },
  { k: 'Signed', v: 'By Jonah, and by Ana' },
  { k: 'Right person', v: 'Printed name matches the case' },
  { k: 'Right letter', v: 'The one HR approved' },
] as const

export const DRIVE_PATH = ['HR', 'Discipline', 'Signed', 'Brooks, Jonah'] as const
export const SIGNED_FILE = 'Brooks_Jonah_written-warning_2026-10-07.pdf'
