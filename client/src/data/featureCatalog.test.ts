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
    const work = FEATURE_GROUPS.find((group) => group.label === 'Matcha Ops')

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
      matcha_ops: true,
      inventory: true,
      inventory_voice: true,
    })
  })

  it('disables dependent features without disabling unrelated prerequisites', () => {
    const features = { matcha_ops: true, inventory: true, inventory_voice: true }

    expect(applyFeatureToggle(features, 'inventory', false)).toEqual({
      matcha_ops: true,
      inventory: false,
      inventory_voice: false,
    })
  })

  it('disables every dependent when a prerequisite is disabled', () => {
    expect(applyFeatureToggle(
      { matcha_work: true, matcha_ops: true, inventory: true, inventory_voice: true },
      'matcha_ops',
      false,
    )).toMatchObject({
      matcha_work: true,
       matcha_ops: false,
       inventory: false,
       inventory_voice: false,
       ems: false,
       werk_lite: false,
    })
  })
})
