import { describe, expect, it } from 'vitest'
import {
  applyFeatureToggle,
  FEATURE_GROUPS,
  FEATURE_KEYS,
  FEATURE_LABELS,
  FEATURE_REQUIRES,
  featureLabel,
  OTHER_GROUP_LABEL,
  withOtherGroup,
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

describe('sales intake feature', () => {
  it('is available and requires inventory', () => {
    const ops = FEATURE_GROUPS.find((group) => group.label === 'Matcha Ops')
    expect(ops?.features.sales_intake).toContain('Sales Intake')
    expect(FEATURE_KEYS).toContain('sales_intake')
    expect(FEATURE_REQUIRES.sales_intake).toEqual(['inventory'])
  })
})

describe('sym-link feature', () => {
  it('is togglable in admin and composable into a custom product', () => {
    // Without a catalog entry the flag is invisible in BOTH admin surfaces —
    // Features.tsx and Products.tsx render from FEATURE_GROUPS and have no
    // catch-all bucket — so it can only be enabled by raw SQL. It shipped that
    // way and this is the guard.
    const core = FEATURE_GROUPS.find((group) => group.label === 'Core HR')

    expect(core?.features.symlink).toContain('Sym-Link')
    expect(FEATURE_KEYS).toContain('symlink')
    expect(FEATURE_LABELS.symlink).toContain('Sym-Link')
  })

  it('has no prerequisite flag', () => {
    // Mirrors the backend: `symlink` is absent from FEATURE_REQUIRES. The
    // credential kind wants a linked employee at apply time, but that is a
    // per-link condition, not a feature dependency.
    expect(FEATURE_REQUIRES.symlink).toBeUndefined()
    expect(applyFeatureToggle({}, 'symlink', true)).toMatchObject({ symlink: true })
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
      sales_intake: false,
      inventory_forecasting: false,
      inventory_waste: false,
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

  it('requires inventory and sales intake', () => {
    expect(FEATURE_REQUIRES.inventory_forecasting).toEqual(['inventory', 'sales_intake'])
    expect(applyFeatureToggle({}, 'inventory_forecasting', true)).toMatchObject({
      matcha_ops: true,
      inventory: true,
      sales_intake: true,
      inventory_forecasting: true,
    })
  })
})

describe('sym-chat feature', () => {
  it('is togglable in admin and requires matcha_work', () => {
    const work = FEATURE_GROUPS.find((group) => group.label === 'Matcha Work')
    expect(work?.features.sym_chat).toContain('Sym-chat')
    expect(FEATURE_KEYS).toContain('sym_chat')
    expect(FEATURE_REQUIRES.sym_chat).toEqual(['matcha_work'])
  })
})

describe('espresso assistant', () => {
  it('is not a company flag: personal Espresso accounts get it', () => {
    expect(FEATURE_KEYS).not.toContain('espresso_assistant')
    expect(FEATURE_REQUIRES).not.toHaveProperty('espresso_assistant')
  })
})

describe('matcha drive feature', () => {
  it('is togglable in admin and requires matcha_work', () => {
    const work = FEATURE_GROUPS.find((group) => group.label === 'Matcha Work')
    expect(work?.features.matcha_drive).toContain('Matcha Drive')
    expect(FEATURE_KEYS).toContain('matcha_drive')
    expect(FEATURE_REQUIRES.matcha_drive).toEqual(['matcha_work'])
  })
})

describe('hr cases feature', () => {
  it('is togglable in admin and requires work + drive', () => {
    const work = FEATURE_GROUPS.find((group) => group.label === 'Matcha Work')
    expect(work?.features.hr_cases).toContain('HR Cases')
    expect(FEATURE_REQUIRES.hr_cases).toEqual(['matcha_work', 'matcha_drive'])
  })
})

describe('withOtherGroup', () => {
  it('adds an Other group for backend flags the catalog does not name, labelled by key', () => {
    const groups = withOtherGroup(['handbooks', 'zz_new_flag', 'aa_new_flag', 'zz_new_flag'])

    expect(groups.slice(0, -1)).toEqual(FEATURE_GROUPS)
    expect(groups.at(-1)).toEqual({
      label: OTHER_GROUP_LABEL,
      features: { aa_new_flag: 'aa_new_flag', zz_new_flag: 'zz_new_flag' },
    })
  })

  it('adds nothing when the catalog names every backend flag', () => {
    expect(withOtherGroup(['handbooks', 'huume'])).toBe(FEATURE_GROUPS)
    expect(withOtherGroup([])).toBe(FEATURE_GROUPS)
  })

  it('does not treat inherited object keys as catalog entries', () => {
    expect(withOtherGroup(['constructor']).at(-1)?.features).toEqual({ constructor: 'constructor' })
    expect(featureLabel('constructor')).toBe('constructor')
  })
})

describe('featureLabel', () => {
  it('uses the catalog name, else the raw key', () => {
    expect(featureLabel('ask_hr')).toContain('Ask HR')
    expect(featureLabel('zz_new_flag')).toBe('zz_new_flag')
  })
})

describe('flags the admin catalog used to miss', () => {
  it('names every one of them', () => {
    for (const key of [
      'acord_forms', 'ask_hr', 'carrier_quotes', 'channel_job_postings', 'coi_tracking',
      'compliance_lite', 'do_readiness', 'handbook_audit', 'handbook_watch', 'huume_code',
      'labor_cost', 'labor_relations', 'paid_channel_creator', 'property', 'tcor',
      'werk_lite_calls_all_members',
    ]) {
      expect(FEATURE_KEYS).toContain(key)
    }
  })

  it('mirrors their backend prerequisites', () => {
    expect(FEATURE_REQUIRES.huume_code).toEqual(['matcha_work'])
    expect(FEATURE_REQUIRES.labor_cost).toEqual(['employee_schedule'])
    expect(applyFeatureToggle({ matcha_work: true, huume_code: true }, 'matcha_work', false)).toMatchObject({
      huume_code: false,
    })
  })
})
