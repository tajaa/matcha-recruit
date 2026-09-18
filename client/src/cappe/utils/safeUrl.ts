// URL-scheme guards for values that originate from other tenants' input.
//
// Creator portfolio/deliverable URLs (`external_url`, `submission_url`,
// `cover_url`, …) are stored as free text and rendered into `href` and CSS
// `url()` sinks on pages a *different* account visits — a brand opening a
// creator's public profile, a creator opening a brand's offer. A stored
// `javascript:` value there is stored XSS against the viewer. The server-side
// counterpart is the `_https` field validator on the same models; this is the
// render-time half, so old rows written before that validator existed are
// also neutralised.

/** The URL, trimmed, only when it is an absolute http(s) URL. Otherwise
 *  `undefined` — callers must not render the sink at all in that case.
 *
 *  `new URL()` does the scheme parsing, which matters: it applies the same
 *  tab/newline stripping the HTML parser does, so `"java\nscript:alert(1)"`
 *  is recognised as the `javascript:` URL the browser would execute rather
 *  than passing a naive `startsWith('http')` test. */
export function safeHttpUrl(u?: string | null): string | undefined {
  if (typeof u !== 'string') return undefined
  const s = u.trim()
  if (!s) return undefined
  let parsed: URL
  try {
    parsed = new URL(s)
  } catch {
    return undefined // relative or unparseable — not an absolute http(s) URL
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return undefined
  return s
}

/** The URL, percent-encoded so it cannot break out of a CSS `url("…")` token,
 *  only when it is an absolute **https** URL. Otherwise `undefined`.
 *
 *  https-only (stricter than `safeHttpUrl`) to match the server's `_https`
 *  validator on the same fields: these are background images on an https page,
 *  where an http URL is blocked as mixed content anyway.
 *
 *  Serialised with `URL.href`, not `encodeURI`: `href` percent-encodes what
 *  needs it and leaves existing escapes alone, whereas `encodeURI` re-encodes
 *  the `%` of an already-encoded URL (`a%20b` → `a%2520b`) and breaks every
 *  image whose path had a space in it. `href` still leaves `'`, `(` and `)`
 *  untouched, and any one of them closes the `url()` token early — hence the
 *  second pass. */
export function safeCssUrl(u?: string | null): string | undefined {
  const safe = safeHttpUrl(u)
  if (!safe || !safe.toLowerCase().startsWith('https:')) return undefined
  return new URL(safe).href.replace(
    /["'()\\]/g,
    (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
  )
}
