import { describe, expect, it } from 'vitest'
import { authLoginPath, GUMMFIT_ADMIN_LOGIN, isGummfitAdminLoginPath, isGummfitAdminPath } from './authPaths'

describe('staff route classification', () => {
  it.each(['/gummfit/admin', '/GUMMFIT/ADMIN/', '/gummfit/%61dmin/models', '/%67ummfit/admin?ignored', '/gummfit/admin/%ZZ'])('keeps %s in the staff realm', (path) => {
    // Callers supply pathname, without a query or fragment.
    const pathname = path.split('?')[0]
    expect(isGummfitAdminPath(pathname)).toBe(true)
    expect(authLoginPath(pathname)).toBe(GUMMFIT_ADMIN_LOGIN)
  })

  it.each(['/gummfit/administrator', '/gummfit%2Fadmin', '/gummfit/admin%2Fmodels', '/%ZZ/admin', '//gummfit/admin', '/admin'])('does not invent a staff boundary in %s', (path) => {
    expect(isGummfitAdminPath(path)).toBe(false)
    expect(authLoginPath(path)).toBe('/login')
  })

  it.each(['/gummfit/admin/login', '/GUMMFIT/ADMIN/LOGIN/', '/gummfit/%61dmin/%6cogin///'])('recognizes equivalent staff login %s', (path) => {
    expect(isGummfitAdminLoginPath(path)).toBe(true)
  })

  it.each(['/gummfit/admin', '/gummfit/admin/logins', '/gummfit/admin/login/models', '/gummfit/admin/login%2F', '/gummfit/admin/%ZZ', '/login'])('does not confuse %s with the staff login', (path) => {
    expect(isGummfitAdminLoginPath(path)).toBe(false)
  })
})
