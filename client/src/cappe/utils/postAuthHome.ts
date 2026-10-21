import { creatorPaths } from '../creators/creatorPaths'
import { writerPaths } from '../magazine/writers/writerPaths'

/** Where an account lands after signing in or confirming its email. */
export function postAuthHome(accountType?: string): string {
  if (accountType === 'creator') return creatorPaths.home
  if (accountType === 'writer') return writerPaths.home
  return '/cappe/sites'
}
