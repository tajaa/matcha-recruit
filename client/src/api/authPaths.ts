export const GUMMFIT_ADMIN_PATH = '/gummfit/admin'
export const GUMMFIT_ADMIN_LOGIN = `${GUMMFIT_ADMIN_PATH}/login`

export function isGummfitAdminPath(pathname: string): boolean {
  return pathname === GUMMFIT_ADMIN_PATH || pathname.startsWith(`${GUMMFIT_ADMIN_PATH}/`)
}

/** Staff sessions on Gummfit must never fall into the customer sign-in flow. */
export function authLoginPath(pathname: string): string {
  return isGummfitAdminPath(pathname) ? GUMMFIT_ADMIN_LOGIN : '/login'
}
