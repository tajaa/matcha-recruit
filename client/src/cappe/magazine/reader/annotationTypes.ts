/** Browser offsets use UTF-16; persisted strings are plain text, never HTML. */
export type ReaderQuote = { exact: string; prefix: string; suffix: string; start: number }
export type ReaderAnnotationBody = {
  kind: 'highlight' | 'underline' | 'comment'
  view: 'pages' | 'text'
  page: number
  quote: ReaderQuote | null
  text: string
}
export type ReaderAnnotation = ReaderAnnotationBody & { id: string }
