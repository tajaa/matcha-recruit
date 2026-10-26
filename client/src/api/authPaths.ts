export const GUMMFIT_ADMIN_PATH = '/gummfit/admin'
export const GUMMFIT_ADMIN_LOGIN = `${GUMMFIT_ADMIN_PATH}/login`

function routeSegment(value = ''): string {
  try { return decodeURIComponent(value).toLowerCase() }
  catch { return '' }
}

export function isGummfitAdminPath(pathname: string): boolean {
  const parts = pathname.split('/')
  return parts[0] === '' && routeSegment(parts[1]) === 'gummfit' && routeSegment(parts[2]) === 'admin'
}

/** Match the router's decoded, case-insensitive path, including trailing slashes.
 * Decode per segment so an encoded slash cannot become a route boundary. */
export function isGummfitAdminLoginPath(pathname: string): boolean {
  const parts = pathname.split('/')
  return isGummfitAdminPath(pathname) && routeSegment(parts[3]) === 'login'
    && parts.slice(4).every((part) => part === '')
}

/** Staff sessions on Gummfit must never fall into the customer sign-in flow. */
export function authLoginPath(pathname: string): string {
  return isGummfitAdminPath(pathname) ? GUMMFIT_ADMIN_LOGIN : '/login'
}
