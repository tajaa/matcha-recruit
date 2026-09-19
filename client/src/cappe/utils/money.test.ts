// parseFloat's truncation is a money bug: "1,299" silently became 1 and was
// saved as a $1.00 price. These cases pin the refusals.
// Run:  npx vitest run src/cappe/utils/money
import { describe, expect, it } from 'vitest'
import { parseMoney, parseMoneyCents, parsePercentBps, parseSignedMoneyCents } from './money'

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

describe('signed option deltas', () => {
  it('accepts a negative delta — a smaller size can cost less', () => {
    expect(parseSignedMoneyCents('-0.50')).toBe(-50)
    expect(parseSignedMoneyCents('2.50')).toBe(250)
    expect(parseSignedMoneyCents('-1,25')).toBe(-125)
  })
  it('still refuses junk', () => {
    expect(parseSignedMoneyCents('--1')).toBeNull()
    expect(parseSignedMoneyCents('-')).toBeNull()
    expect(parseSignedMoneyCents('1-')).toBeNull()
  })
  it('a plain price stays unsigned', () => {
    expect(parseMoneyCents('-5')).toBeNull()
  })
})

describe('percentage rates', () => {
  it('accepts three decimals and rounds to whole basis points', () => {
    expect(parsePercentBps('8.875')).toBe(888)
    expect(parsePercentBps('8.75')).toBe(875)
    expect(parsePercentBps('0')).toBe(0)
  })
  it('refuses a fourth decimal, a sign, or a percent mark', () => {
    expect(parsePercentBps('8.8755')).toBeNull()
    expect(parsePercentBps('-1')).toBeNull()
    expect(parsePercentBps('8.75%')).toBeNull()
  })
})

