import { describe, expect, it } from 'vitest'
import { gramsFromText, textFromGrams, weightUnit } from './weight'

describe('weights', () => {
  it('types weights in pounds where the store is in a pound country, kilograms elsewhere', () => {
    expect(weightUnit('US')).toBe('lb')
    expect(weightUnit('fr')).toBe('kg')
    expect(weightUnit(null)).toBe('kg')
  })

  it('stores grams and reads them back', () => {
    expect(gramsFromText('2', 'lb')).toBe(907)
    expect(gramsFromText('1,5', 'kg')).toBe(1500)
    expect(textFromGrams(1500, 'kg')).toBe('1.5')
    expect(textFromGrams(907, 'lb')).toBe('2')
    expect(textFromGrams(null, 'kg')).toBe('')
  })

  it('tells blank from unreadable', () => {
    expect(gramsFromText('  ', 'kg')).toBeNull()
    expect(gramsFromText('2lb', 'lb')).toBeUndefined()
    expect(gramsFromText('1.2.3', 'kg')).toBeUndefined()
  })
})
