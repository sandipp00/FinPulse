import { useEffect, useState } from 'react'
import { getVixCurve } from '../api/finpulse'
import SeriesChart from './SeriesChart'
import { curvePoints, shapeReading } from '../lib/vixCurve'

const REFRESH_MS = 60_000
const W = 420
const H = 150

/** Expected S&P 500 volatility for five horizons now, and VIX3M / VIX over time. */
export default function VixCurvePanel() {
  const [state, setState] = useState({ data: null, error: '' })

  useEffect(() => {
    let cancelled = false
    const load = () => getVixCurve()
      .then((data) => { if (!cancelled) setState({ data, error: '' }) })
      .catch((error) => { if (!cancelled) setState((s) => ({ ...s, error: error.message || 'Unavailable' })) })
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const { data, error } = state
  const points = data ? curvePoints(data.curve, W, H) : []

  return (
    <section className="panel vix-panel" aria-label="VIX term structure">
      <div className="panel-heading">
        <div>
          <h2>Volatility term structure</h2>
          <p>Expected S&amp;P 500 volatility over five horizons, from Cboe&apos;s VIX indices (via Yahoo)</p>
        </div>
      </div>
      {!data && <p className="pulse-empty">{error ? `Unavailable: ${error}` : 'Loading…'}</p>}
      {data && (
        <div className="vix-grid">
          <div>
            <svg viewBox={`0 0 ${W} ${H + 34}`} className="vix-curve" role="img" aria-label="VIX by horizon">
              <polyline points={points.filter((p) => p.y != null).map((p) => `${p.x},${p.y}`).join(' ')} />
              {points.map((p) => (
                <g key={p.symbol}>
                  {p.y != null && <circle cx={p.x} cy={p.y} r="3.5" />}
                  {p.y != null && <text x={p.x} y={p.y - 9} textAnchor="middle" className="vix-value">{p.value.toFixed(1)}</text>}
                  <text x={p.x} y={H + 24} textAnchor="middle" className="vix-tenor">{p.label.replace(' (VIX)', '')}</text>
                </g>
              ))}
            </svg>
            <p className="vix-summary">
              VIX3M / VIX: <b>{data.ratio == null ? '—' : data.ratio.toFixed(2)}</b>, {shapeReading(data.shape)}
            </p>
            {data.ratio_percentile != null && (
              <p className="deriv-note">
                A lower ratio (more near-term fear) than on {100 - data.ratio_percentile}% of the {data.ratio_history.length} days shown; below 1 on {data.ratio_backwardation_share}% of them.
              </p>
            )}
            {data.errors.length > 0 && <p className="deriv-note ix-warn">Missing: {data.errors.join('; ')}</p>}
          </div>
          <div>
            <h3 className="at-section-title">VIX3M / VIX, daily</h3>
            <div className="ix-chart-wrap deriv-chart"><SeriesChart points={data.ratio_history} precision={2} /></div>
            <p className="deriv-note">{data.notes.join(' ')}</p>
          </div>
        </div>
      )}
    </section>
  )
}
