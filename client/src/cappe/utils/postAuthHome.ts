import { creatorPaths } from '../creators/creatorPaths'
import { writerPaths } from '../magazine/writers/writerPaths'
import { readerPaths } from '../magazine/shelf/readerPaths'

/** Where an account lands after signing in or confirming its email. */
export function postAuthHome(accountType?: string): string {
  if (accountType === 'creator') return creatorPaths.home
  if (accountType === 'writer') return writerPaths.home
  if (accountType === 'reader') return readerPaths.home
  return '/cappe/sites'
}
