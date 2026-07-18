import {
  CATEGORY_LABELS,
  CATEGORY_SHORT_LABELS,
} from '../../../generated/complianceCategories'

export function getCategoryLabel(cat: string) {
  return CATEGORY_LABELS[cat] ?? cat
}

export function getShortLabel(cat: string) {
  return CATEGORY_SHORT_LABELS[cat] ?? cat
}
