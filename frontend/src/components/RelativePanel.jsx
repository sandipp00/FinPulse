import { useEffect, useMemo, useState } from 'react'
import { getRelative } from '../api/finpulse'
import SeriesChart from './SeriesChart'

const WINDOWS = [20, 60, 120]

const METRICS = [
  ['beta', 'Beta', (v) => v?.toFixed(2), 'How much the asset moved per 1% move in the benchmark: cov(asset, benchmark) / var(benchmark).'],
  ['correlation', 'Correlation', (v) => v?.toFixed(2), 'Pearson correlation of daily returns, -1 to 1, on shared dates.'],
  ['r_squared', 'R²', (v) => v?.toFixed(2), 'Share of the asset\'s daily variance that moved with the benchmark (correlation squared).'],
  ['asset_return_pct', 'Asset return / yr', pct, 'Annualized (CAGR) over the shared window, using calendar time.'],
  ['benchmark_return_pct', 'Benchmark return / yr', pct, 'Annualized (CAGR) over the same window.'],
  ['excess_return_pct', 'Excess return / yr', pct, 'Asset minus benchmark annualized return.'],
  ['tracking_error_pct', 'Tracking error / yr', (v) => (v == null ? null : `${v.toFixed(2)}%`), 'Annualized standard deviation of the daily return difference.'],
  ['information_ratio', 'Information ratio', (v) => v?.toFixed(2), 'Annualized mean return difference divided by tracking error.'],
]

function pct(value) {
  if (value == null) return null
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function useRelative(symbol, benchmark, span) {
  const key = `${symbol}|${benchmark}|${span}`
  const [result, setResult] = useState({ key: null, data: null, error: '' })
  useEffect(() => {
    let cancelled = false
    getRelative(symbol, benchmark, span)
      .then((data) => { if (!cancelled) setResult({ key, data, error: '' }) })
      .catch((err) => { if (!cancelled) setResult({ key, data: null, error: err.message || 'Unable to compare.' }) })
    return () => { cancelled = true }
  }, [key, symbol, benchmark, span])
  const loading = result.key !== key
  return { data: loading ? null : result.data, loading, error: loading ? '' : result.error }
}

function AssetRow({ name, stats }) {
  if (!stats) return null
  return (
    <tr>
      <th scope="row">{name}</th>
      <td className="num">{pct(stats.annualized_return_pct) ?? '—'}</td>
      <td className="num">{stats.volatility_pct == null ? '—' : `${stats.volatility_pct.toFixed(2)}%`}</td>
      <td className="num">{stats.max_drawdown_pct == null ? '—' : `${stats.max_drawdown_pct.toFixed(2)}%`}</td>
      <td>{stats.drawdown_peak ? `${stats.drawdown_peak} → ${stats.drawdown_trough}` : '—'}</td>
      <td>{stats.drawdown_peak ? (stats.recovered ? `recovered ${stats.drawdown_recovery} (${stats.drawdown_days} days)` : `not yet (${stats.drawdown_days} days so far)`) : '—'}</td>
    </tr>
  )
}

/** Benchmark-relative statistics for the explorer's two instruments (daily bars only). */
export default function RelativePanel({ symbol, benchmark }) {
  const [span, setSpan] = useState(60)
  const { data, loading, error } = useRelative(symbol, benchmark, span)
  const points = useMemo(
    () => (data ? data.rolling.map((row) => ({ time: row.date, value: row.correlation })) : []),
    [data],
  )

  return (
    <section className="panel ix-returns" aria-label={`${symbol} relative to ${benchmark}`}>
      <h2>Relative to {benchmark} <span>daily returns on shared dates</span></h2>
      {loading && <p className="ix-footnote">Calculating…</p>}
      {error && <p className="ix-footnote ix-error">{error}</p>}
      {data && (
        <>
          <p className="ix-footnote">
            {data.overlap} shared days{data.start_date ? `, ${data.start_date} to ${data.end_date}` : ''};
            annualized with {data.periods_per_year} periods a year.
            {data.note && <span className="ix-warn"> {data.note}</span>}
          </p>
          <dl className="ix-stats">
            {METRICS.map(([key, label, format, help]) => (
              <div className="ix-stat" key={key} title={help}>
                <dt>{label}</dt>
                <dd className="num">{format(data.metrics[key]) ?? '—'}</dd>
              </div>
            ))}
          </dl>

          <div className="table-scroll">
            <table className="rel-table">
              <thead>
                <tr><th /><th>Return / yr</th><th>Volatility / yr</th><th>Max drawdown</th><th>Peak → trough</th><th>Recovery</th></tr>
              </thead>
              <tbody>
                <AssetRow name={symbol} stats={data.assets[symbol]} />
                <AssetRow name={benchmark} stats={data.assets[benchmark]} />
              </tbody>
            </table>
          </div>

          {points.length > 0 && (
            <>
              <div className="ix-head rel-head">
                <h3>Rolling {span}-day correlation</h3>
                <div className="range-control" role="group" aria-label="Rolling window">
                  {WINDOWS.map((item) => (
                    <button key={item} onClick={() => setSpan(item)} className={item === span ? 'range-active' : ''} aria-pressed={item === span}>
                      {item}d
                    </button>
                  ))}
                </div>
              </div>
              <div className="ix-chart-wrap rel-chart"><SeriesChart points={points} /></div>
            </>
          )}
          <p className="ix-footnote">{data.methodology.caveat} Definitions: hover a figure, or see docs/METHODOLOGY.md.</p>
        </>
      )}
    </section>
  )
}
