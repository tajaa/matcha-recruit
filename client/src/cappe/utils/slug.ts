// Preview of the subdomain the server will derive from a site name. Mirrors
// `safe_subdomain_base` (server/app/cappe/services/common.py): lowercase,
// hyphenate, and cap at one DNS label. It is only a preview: the server also
// steers off reserved words and numbers a name that is already taken.
const SUBDOMAIN_MAX_LEN = 63

export function subdomainPreview(name: string, fallback = 'your-name'): string {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return slug.slice(0, SUBDOMAIN_MAX_LEN).replace(/-+$/, '') || fallback
}
