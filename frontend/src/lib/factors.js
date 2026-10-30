// Fama-French factor exposure (backend/famafrench.py) in plain words.

// US indices with factor exposure; every followed US stock has it too.
export const FACTOR_INDICES = ['^GSPC', '^DJI', '^IXIC', '^RUT', '^NYA']

export const FACTOR_LABEL = { 'Mkt-RF': 'Market', SMB: 'Size', HML: 'Value', Mom: 'Momentum' }

/** Whether an exposure is distinguishable from zero (|t| of about 2 or more). */
export const significant = (term) => term?.t_stat != null && Math.abs(term.t_stat) >= 2

/** One line per factor saying what the exposure means. */
export function factorReading(name, term) {
  if (!term) return ''
  const v = term.value
  if (!significant(term) && name !== 'Mkt-RF') return 'No clear tilt (could be chance).'
  switch (name) {
    case 'Mkt-RF':
      if (v >= 1.15) return `Swings more than the market: about ${v.toFixed(2)}% per 1% market move.`
      if (v <= 0.85) return `Swings less than the market: about ${v.toFixed(2)}% per 1% market move.`
      return 'Moves roughly one-for-one with the market.'
    case 'SMB':
      return v > 0 ? 'Behaves like smaller companies.' : 'Behaves like large companies.'
    case 'HML':
      return v > 0 ? 'Leans value: moves with cheaper, asset-heavy companies.' : 'Leans growth: moves with expensive, fast-growing companies.'
    case 'Mom':
      return v > 0 ? 'Moves with recent winners.' : 'Moves against recent winners.'
    default:
      return ''
  }
}
