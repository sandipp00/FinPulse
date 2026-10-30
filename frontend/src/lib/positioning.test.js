import { describe, expect, it } from 'vitest'
import { percentileReading } from './positioning'

describe('percentileReading', () => {
  it('names the extremes and the middle, relative to the market itself', () => {
    expect(percentileReading(100)).toMatch(/most bullish in three years/)
    expect(percentileReading(1)).toMatch(/most bearish in three years/)
    expect(percentileReading(78)).toMatch(/more bullish than usual/)
    expect(percentileReading(24)).toMatch(/more bearish than usual/)
    expect(percentileReading(50)).toMatch(/middle/)
    expect(percentileReading(null)).toMatch(/Not enough/)
  })
})
