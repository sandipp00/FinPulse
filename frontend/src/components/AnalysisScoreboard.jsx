import { useEffect, useMemo, useState } from 'react'
import { getAnalysisScoreboard } from '../api/finpulse'
import { CLASS_LABEL, CLASS_ORDER } from '../lib/asset'
import { rsiZone, sortRows } from '../lib/analysis'
import { formatPercent } from '../lib/format'

const COLUMNS = [
  { key: 'name', label: 'Asset' },
  { key: 'return_1w', label: '1W', pct: true },
  { key: 'return_1m', label: '1M', pct: true },
  { key: 'return_3m', label: '3M', pct: true },
  { key: 'return_ytd', label: 'YTD', pct: true },
  { key: 'return_1y', label: '1Y', pct: true },
  { key: 'volatility_1y', label: 'Vol 1Y', pct: true, plain: true },
  { key: 'max_drawdown', label: 'Max fall', pct: true },
  { key: 'from_high_52w', label: 'From 52w high', pct: true },
  { key: 'rsi_14', label: 'RSI' },
  { key: 'trend', label: 'Trend' },
]

const TREND_LABEL = { up: '▲ Up', down: '▼ Down', mixed: '◆ Mixed' }

function Cell({ column, row }) {
  const value = row[column.key]
  if (value == null) return <td className="num sb-empty">—</td>
  if (column.pct && column.plain) return <td className="num">{(value * 100).toFixed(1)}%</td>  // a level, not a change
  if (column.pct) return <td className={`num ${value >= 0 ? 'up' : 'down'}`}>{formatPercent(value * 100, 1)}</td>
  if (column.key === 'rsi_14') return <td className={`num sb-rsi-${rsiZone(value)}`}>{value.toFixed(0)}</td>
  if (column.key === 'trend') return <td className={`sb-trend sb-trend-${value}`}>{TREND_LABEL[value]}</td>
  return <td>{value}</td>
}

/** Every asset's headline figures in one sortable table; a row opens its full analysis. */
export default function AnalysisScoreboard({ selected, onSelect }) {
  const [state, setState] = useState({ data: null, error: '' })
  const [assetClass, setAssetClass] = useState('all')
  const [sort, setSort] = useState({ key: 'return_1y', direction: 'desc' })

  useEffect(() => {
    let cancelled = false
    getAnalysisScoreboard()
      .then((data) => !cancelled && setState({ data, error: '' }))
      .catch((err) => !cancelled && setState({ data: null, error: err.message || 'Unable to load the scoreboard.' }))
    return () => {
      cancelled = true
    }
  }, [])

  const rows = useMemo(() => {
    const all = state.data?.rows ?? []
    const filtered = assetClass === 'all' ? all : all.filter((row) => row.asset.asset_class === assetClass)
    return sortRows(filtered, sort.key, sort.direction)
  }, [state.data, assetClass, sort])

  const toggle = (key) => setSort((current) => (
    current.key === key ? { key, direction: current.direction === 'desc' ? 'asc' : 'desc' } : { key, direction: key === 'name' ? 'asc' : 'desc' }
  ))

  return (
    <section className="panel sb-panel" aria-label="Asset scoreboard">
      <div className="panel-heading">
        <div>
          <h2>Scoreboard: every asset</h2>
          <p>Returns, risk and trend from daily history. Click a column to sort, a row for the full analysis.</p>
        </div>
      </div>
      <div className="at-tabs sb-tabs" role="tablist" aria-label="Asset class">
        {['all', ...CLASS_ORDER].map((key) => (
          <button key={key} role="tab" aria-selected={assetClass === key} className={assetClass === key ? 'at-tab-active' : ''} onClick={() => setAssetClass(key)}>
            {key === 'all' ? 'All' : CLASS_LABEL[key]}
          </button>
        ))}
      </div>
      {!state.data && !state.error && <p className="at-empty">Analysing every asset… (the first load fetches each history)</p>}
      {state.error && <p className="at-empty ix-error">{state.error}</p>}
      {state.data && (
        <div className="table-scroll">
          <table className="sb-table">
            <thead>
              <tr>
                {COLUMNS.map((column) => (
                  <th key={column.key} className={column.key === 'name' ? '' : 'num'}>
                    <button onClick={() => toggle(column.key)} aria-label={`Sort by ${column.label}`}>
                      {column.label}{sort.key === column.key ? (sort.direction === 'desc' ? ' ↓' : ' ↑') : ''}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.asset.id}
                  className={`sb-row ${row.asset.id === selected ? 'sb-row-active' : ''}`}
                  onClick={() => onSelect(row.asset.id)}
                  title={row.error ?? `From ${row.source?.provider} (${row.source?.symbol}), ${row.source?.days} days to ${row.last_date}`}
                >
                  <td>
                    <span className="sb-name">{row.asset.name}</span>
                    <span className="sb-sub">{CLASS_LABEL[row.asset.asset_class]}{row.error ? ` · ${row.error}` : ''}</span>
                  </td>
                  {COLUMNS.slice(1).map((column) => <Cell key={column.key} column={column} row={row} />)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {state.data && <p className="ix-footnote">{state.data.notes.join(' ')}</p>}
    </section>
  )
}
