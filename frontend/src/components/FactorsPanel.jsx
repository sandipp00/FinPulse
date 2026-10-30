import { useEffect, useState } from 'react'
import { getFactorExposure } from '../api/finpulse'
import { FACTOR_LABEL, factorReading, significant } from '../lib/factors'

// The bar spans -2 to +2 around its centre; the market beta is centred on 1 instead of 0.
const SCALE = 2

/** How a US stock or index moved with the market, size, value and momentum factors. */
export default function FactorsPanel({ symbol }) {
  const [state, setState] = useState({ symbol: null, data: null, error: '' })

  useEffect(() => {
    let cancelled = false
    getFactorExposure(symbol)
      .then((data) => { if (!cancelled) setState({ symbol, data, error: '' }) })
      .catch((error) => { if (!cancelled) setState({ symbol, data: null, error: error.message || 'Unavailable' }) })
    return () => {
      cancelled = true
    }
  }, [symbol])

  const current = state.symbol === symbol
  const data = current ? state.data : null
  const error = current ? state.error : ''

  return (
    <section className="panel at-figures" aria-label="Factor exposure">
      <h3 className="at-section-title">Factor exposure (Fama-French)</h3>
      {!current && <p className="pulse-empty">Fitting the factor model…</p>}
      {error && <p className="pulse-empty">Factor exposure is unavailable: {error}</p>}
      {data && (
        <>
          {data.stale && <p className="pulse-empty ix-warn">The factor library is not answering ({data.stale}); using the last files.</p>}
          <p className="factor-summary">
            Daily returns, {data.start_date} to {data.end_date} ({data.observations} days). The factors explain{' '}
            <b>{data.r_squared == null ? '—' : `${Math.round(data.r_squared * 100)}%`}</b> of the day-to-day moves.
          </p>
          <ul className="factor-list">
            {Object.entries(data.betas).map(([name, term]) => {
              const centre = name === 'Mkt-RF' ? 1 : 0
              const offset = Math.max(-1, Math.min(1, (term.value - centre) / SCALE))
              return (
                <li key={name} className={significant(term) ? '' : 'factor-faint'}>
                  <span className="factor-name">{FACTOR_LABEL[name]}</span>
                  <span className="factor-bar" aria-hidden="true">
                    <i
                      className={offset >= 0 ? 'up-bg' : 'down-bg'}
                      style={{ left: offset >= 0 ? '50%' : `${50 + offset * 50}%`, width: `${Math.abs(offset) * 50}%` }}
                    />
                  </span>
                  <span className="factor-value num">{term.value.toFixed(2)}</span>
                  <span className="factor-t num" title="t-statistic">t {term.t_stat ?? '—'}</span>
                  <small>{factorReading(name, term)}</small>
                </li>
              )
            })}
          </ul>
          <p className="factor-summary">
            Alpha (return not explained by the factors): <b>{data.alpha_annual_pct > 0 ? '+' : ''}{data.alpha_annual_pct}% a year</b>{' '}
            (t {data.alpha_t_stat}){Math.abs(data.alpha_t_stat ?? 0) < 2 ? ', which could be chance.' : '.'}
          </p>
          <p className="deriv-note">{data.notes.slice(1).join(' ')} {data.notes[0]}</p>
        </>
      )}
    </section>
  )
}
