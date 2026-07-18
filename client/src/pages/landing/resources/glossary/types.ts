export type GlossaryTerm = {
  slug: string
  term: string
  abbreviation?: string
  short: string
  definition: string
  related?: string[]
  category: 'law' | 'agency' | 'concept' | 'tax' | 'leave' | 'comp'
}
