import { describe, expect, it } from 'vitest'
import { isLiveMetal, metalsMarketOpen } from './metals'

// New York is UTC-4 until 2026-11-01, then UTC-5.
const ny = (iso) => new Date(iso)

describe('metalsMarketOpen', () => {
  it('is open on weekdays outside the 17:00-18:00 New York break', () => {
    expect(metalsMarketOpen(ny('2026-10-29T14:00:00Z'))).toBe(true) // Thu 10:00
    expect(metalsMarketOpen(ny('2026-10-29T21:30:00Z'))).toBe(false) // Thu 17:30 break
    expect(metalsMarketOpen(ny('2026-10-29T22:00:00Z'))).toBe(true) // Thu 18:00
  })

  it('is closed from Friday 17:00 to Sunday 18:00 New York time', () => {
    expect(metalsMarketOpen(ny('2026-10-30T20:59:00Z'))).toBe(true) // Fri 16:59
    expect(metalsMarketOpen(ny('2026-10-30T21:00:00Z'))).toBe(false) // Fri 17:00
    expect(metalsMarketOpen(ny('2026-10-31T15:00:00Z'))).toBe(false) // Sat
    expect(metalsMarketOpen(ny('2026-11-01T22:59:00Z'))).toBe(false) // Sun 17:59 (UTC-5)
    expect(metalsMarketOpen(ny('2026-11-01T23:00:00Z'))).toBe(true) // Sun 18:00
  })
})

describe('isLiveMetal', () => {
  it('recognises ticks from the metals feed', () => {
    expect(isLiveMetal({ symbol: 'XAU/USDT', asset_class: 'commodity' })).toBe(true)
    expect(isLiveMetal({ symbol: 'BTC/USDT', asset_class: 'crypto' })).toBe(false)
    expect(isLiveMetal(undefined)).toBe(false)
  })
})
