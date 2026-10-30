import { describe, expect, it } from 'vitest'
import { formatCountdown, fxMarketOpen, sessionBar, sessionStatus, sortExchanges } from './marketHours'

const session = { start: 1000, end: 4600, estimated: false }

describe('market hours', () => {
  it('says whether a session is open and how long until that changes', () => {
    expect(sessionStatus(session, 400)).toEqual({ state: 'closed', seconds: 600, estimated: false })
    expect(sessionStatus(session, 1600)).toEqual({ state: 'open', seconds: 3000, estimated: false })
    expect(sessionStatus(session, 5000).state).toBe('closed')
    expect(sessionStatus(null, 0)).toEqual({ state: 'unknown', seconds: null })
  })

  it('formats countdowns to the minute', () => {
    expect(formatCountdown(59)).toBe('0m')
    expect(formatCountdown(45 * 60)).toBe('45m')
    expect(formatCountdown(2 * 3600 + 14 * 60 + 30)).toBe('2h 14m')
    expect(formatCountdown(3 * 86400 + 4 * 3600)).toBe('3d 4h')
    expect(formatCountdown(null)).toBe('—')
  })

  it('places a session inside a window, clipped at its edges', () => {
    expect(sessionBar(session, 0, 10000)).toEqual({ left: 10, width: 36 })
    expect(sessionBar(session, 2000, 6000)).toEqual({ left: 0, width: 65 })
    expect(sessionBar(session, 5000, 9000)).toBeNull()
  })

  it('lists open exchanges first, closing soonest, then the next to open', () => {
    const exchanges = [
      { id: 'later', session: { start: 9000, end: 12000 } },
      { id: 'unknown', session: null },
      { id: 'open-long', session: { start: 0, end: 8000 } },
      { id: 'open-short', session: { start: 0, end: 3000 } },
      { id: 'soon', session: { start: 2500, end: 9000 } },
    ]
    expect(sortExchanges(exchanges, 2000).map((e) => e.id)).toEqual(['open-short', 'open-long', 'soon', 'later', 'unknown'])
  })

  it('knows the FX week', () => {
    expect(fxMarketOpen(new Date('2026-10-30T14:00:00Z'))).toBe(true) // Fri 10:00 New York
    expect(fxMarketOpen(new Date('2026-10-30T21:30:00Z'))).toBe(false) // Fri 17:30
    expect(fxMarketOpen(new Date('2026-11-01T23:00:00Z'))).toBe(true) // Sun 18:00 EST
  })
})
