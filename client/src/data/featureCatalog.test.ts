import { describe, expect, it } from 'vitest'
import {
  applyFeatureToggle,
  FEATURE_GROUPS,
  FEATURE_KEYS,
  FEATURE_LABELS,
  FEATURE_REQUIRES,
} from './featureCatalog'

describe('inventory voice feature', () => {
  it('is available to business and product feature controls', () => {
    const work = FEATURE_GROUPS.find((group) => group.label === 'Matcha Work')

    expect(work?.features.inventory_voice).toBeDefined()
    expect(FEATURE_KEYS).toContain('inventory_voice')
    expect(FEATURE_LABELS.inventory_voice).toContain('Inventory Voice Audit')
  })

  it('requires inventory', () => {
    expect(FEATURE_REQUIRES.inventory_voice).toEqual(['inventory'])
  })
})

describe('applyFeatureToggle', () => {
  it('enables the complete prerequisite chain', () => {
    expect(applyFeatureToggle({}, 'inventory_voice', true)).toMatchObject({
      matcha_work: true,
      inventory: true,
      inventory_voice: true,
    })
  })

  it('disables dependent features without disabling unrelated prerequisites', () => {
    const features = { matcha_work: true, inventory: true, inventory_voice: true }

    expect(applyFeatureToggle(features, 'inventory', false)).toEqual({
      matcha_work: true,
      inventory: false,
      inventory_voice: false,
    })
  })

  it('disables every dependent when a prerequisite is disabled', () => {
    expect(applyFeatureToggle(
      { matcha_work: true, inventory: true, inventory_voice: true },
      'matcha_work',
      false,
    )).toMatchObject({
      matcha_work: false,
      inventory: false,
      inventory_voice: false,
      ems: false,
      huume: false,
      werk_lite: false,
    })
  })
})
