import type { JDContent } from './types'
import { hospitality } from './hospitality'
import { healthcare } from './healthcare'
import { retail } from './retail'
import { foodService } from './foodService'
import { trades } from './trades'
import { manufacturing } from './manufacturing'
import { administrative } from './administrative'
import { technology } from './technology'
import { sales } from './sales'

export type { JDContent } from './types'
export { EEO_STATEMENT } from './eeo'

export const JD_CONTENT: Record<string, JDContent> = {
  ...hospitality,
  ...healthcare,
  ...retail,
  ...foodService,
  ...trades,
  ...manufacturing,
  ...administrative,
  ...technology,
  ...sales,
}
