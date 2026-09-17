// parseFloat's truncation is a money bug: "1,299" silently became 1 and was
// saved as a $1.00 price. These cases pin the refusals.
// Run:  npx vitest run src/cappe/utils/money
import { describe, expect, it } from 'vitest'
import { parseMoney, parseMoneyCents } from './money'

describe('parseMoney', () => {
  it('parses whole and decimal amounts', () => {
    expect(parseMoney('12')).toBe(12)
    expect(parseMoney('12.5')).toBe(12.5)
    expect(parseMoney('12.50')).toBe(12.5)
    expect(parseMoney('0')).toBe(0)
    expect(parseMoney('  8.75 ')).toBe(8.75)
  })

  it('reads a lone comma as the decimal separator', () => {
    expect(parseMoney('12,50')).toBe(12.5)
  })

  it('refuses thousands grouping rather than truncating it', () => {
    // parseFloat('1,299') is 1 — a $1,299 product saved as $1.00.
    expect(parseMoney('1,299')).toBeNull()
    expect(parseMoney('1,299.00')).toBeNull()
  })

  it('refuses trailing junk instead of truncating at it', () => {
    expect(parseMoney('12abc')).toBeNull()
    expect(parseMoney('12.5.7')).toBeNull()
    expect(parseMoney('$12')).toBeNull()
  })

  it('refuses more than two decimal places', () => {
    expect(parseMoney('12.345')).toBeNull()
  })

  it('refuses negatives, exponents and empty input', () => {
    expect(parseMoney('-5')).toBeNull()
    expect(parseMoney('1e3')).toBeNull()
    expect(parseMoney('')).toBeNull()
    expect(parseMoney('   ')).toBeNull()
    expect(parseMoney(undefined as unknown as string)).toBeNull()
  })
})

describe('parseMoneyCents', () => {
  it('converts to integer cents', () => {
    expect(parseMoneyCents('12.34')).toBe(1234)
    expect(parseMoneyCents('0.07')).toBe(7)
    expect(parseMoneyCents('8.75')).toBe(875)
  })

  it('propagates a refusal as null, never 0', () => {
    expect(parseMoneyCents('1,299')).toBeNull()
    expect(parseMoneyCents('abc')).toBeNull()
  })
})
