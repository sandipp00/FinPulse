import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { formatPercent, getAssetDetails } from '../lib/format'

// Column definitions: the tooltip explains the measure in plain words.
const COLUMNS = [
  { key: 'annualized_volatility_pct', label: 'Volatility', digits: 1, plain: true,
    help: 'How much the price swings, per year (standard deviation of daily returns, annualized).' },
  { key: 'recent_volatility_pct', label: 'Last 30 days', digits: 1, plain: true,
    help: 'The same measure over only the latest 30 daily returns. Higher than the long-run figure means it has been choppier lately.' },
  { key: 'max_drawdown_pct', label: 'Worst fall', digits: 1,
    help: 'The biggest drop from a peak to a later low in the data.' },
  { key: 'current_drawdown_pct', label: 'Below high now', digits: 1,
    help: 'How far the latest close is below the highest close so far. 0% means it is at a new high.' },
  { key: 'var_95_pct', label: '1-in-20 day', digits: 2,
    help: 'Value at risk: on 1 trading day in 20 the loss was this large or worse (5th percentile of daily returns).' },
  { key: 'expected_shortfall_pct', label: 'Avg bad day', digits: 2,
    help: 'The average return on those worst 1-in-20 days.' },
  { key: 'worst_day_pct', label: 'Worst day', digits: 1,
    help: 'The single worst daily return in the data.' },
  { key: 'sharpe_ratio', label: 'Sharpe', digits: 2, plain: true, raw: true,
    help: 'Return per unit of volatility (zero risk-free rate). Higher is better; below 0 means it lost money.' },
]

function format(column, value) {
  if (value == null) return '—'
  if (column.raw) return Number(value).toFixed(column.digits)
  return column.plain ? `${Number(value).toFixed(column.digits)}%` : formatPercent(value, column.digits)
}

const SOURCE_LABEL = { binance: 'Binance daily', database: 'Stored history' }

export default function RiskTable({ assets }) {
  const [sort, setSort] = useState({ key: 'annualized_volatility_pct', direction: 'desc' })

  const rows = useMemo(() => {
    const factor = sort.direction === 'desc' ? -1 : 1
    return [...assets].sort((a, b) => {
      const x = a[sort.key]
      const y = b[sort.key]
      if (x == null) return 1
      if (y == null) return -1
      return (x - y) * factor
    })
  }, [assets, sort])

  const sortBy = (key) => setSort((current) => ({
    key,
    direction: current.key === key && current.direction === 'desc' ? 'asc' : 'desc',
  }))

  return (
    <div className="table-scroll">
      <table className="market-table risk-table">
        <thead>
          <tr>
            <th>ASSET</th>
            {COLUMNS.map((column) => (
              <th key={column.key} aria-sort={sort.key === column.key ? (sort.direction === 'desc' ? 'descending' : 'ascending') : 'none'}>
                <button className="th-sort" onClick={() => sortBy(column.key)} title={column.help}>
                  {column.label.toUpperCase()}
                  {sort.key === column.key && (sort.direction === 'desc' ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((asset) => {
            const details = getAssetDetails(asset.symbol)
            return (
              <tr key={asset.symbol}>
                <td>
                  <div className="asset-cell">
                    <span
                      className="asset-icon"
                      style={{ color: details.color, borderColor: `${details.color}44`, background: `${details.color}12` }}
                    >
                      {asset.symbol[0] === '^' ? 'N' : asset.symbol[0]}
                    </span>
                    <span>
                      <strong>{asset.symbol}</strong>
                      <small>{details.name} · {SOURCE_LABEL[asset.source] ?? asset.source}</small>
                    </span>
                  </div>
                </td>
                {COLUMNS.map((column) => {
                  const value = asset[column.key]
                  const loss = !column.plain && value != null && value < 0
                  return (
                    <td key={column.key} className={`price-cell ${loss ? 'tone-down' : ''}`}>
                      {format(column, value)}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
