import { useMemo, memo } from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { usePrices } from '../hooks/usePrices'
import { formatPercent, formatPrice } from '../lib/format'

const RANGES = ['1D', '1W', '1M', '3M', '1Y']
const RANGE_DAYS = { '1D': 2, '1W': 7, '1M': 30, '3M': 90, '1Y': 365 }

function PriceChart({
  assets,
  selectedSymbol,
  onSelectSymbol,
  range,
  onRangeChange,
}) {
  const { prices, loading, error } = usePrices(selectedSymbol)

  const chartData = useMemo(() => {
    const sorted = [...prices].sort(
      (a, b) => new Date(a.timestamp) - new Date(b.timestamp),
    )
    const days = RANGE_DAYS[range]
    const visible = days ? sorted.slice(-Math.min(days, sorted.length)) : sorted

    return visible.map((item) => ({
      date: new Date(item.timestamp).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
      }),
      timestamp: item.timestamp,
      price: Number(item.close),
      volume: Number(item.volume),
    })).filter((item) => Number.isFinite(item.price))
  }, [prices, range])

  const selectedAsset = assets.find((asset) => asset.symbol === selectedSymbol)
  const latestPrice = chartData.at(-1)?.price
  const firstPrice = chartData[0]?.price
  const chartReturn = firstPrice ? ((latestPrice / firstPrice) - 1) * 100 : null

  return (
    <div className="panel performance-panel">
      <div className="panel-heading">
        <div>
          <h2>Historical price analytics</h2>
          <p>Closing prices loaded from your SQLite database</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedSymbol}
            onChange={(event) => onSelectSymbol(event.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200"
            aria-label="Select asset for historical chart"
          >
            {assets.map((asset) => (
              <option key={asset.symbol} value={asset.symbol}>{asset.symbol}</option>
            ))}
          </select>
          <div className="range-control">
            {RANGES.map((item) => (
              <button
                key={item}
                onClick={() => onRangeChange(item)}
                className={range === item ? 'range-active' : ''}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="chart-summary">
        <strong>{latestPrice == null ? '—' : formatPrice(latestPrice, selectedSymbol)}</strong>
        {chartReturn != null && (
          <span className={`change-pill ${chartReturn >= 0 ? 'positive' : 'negative'}`}>
            {chartReturn >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {formatPercent(chartReturn)}
          </span>
        )}
        <span className="text-xs text-slate-500">
          {selectedAsset ? `${selectedAsset.observations} stored observations` : 'Historical data'}
        </span>
      </div>

      <div className="chart-legend">
        <span><i className="legend-dot emerald" /> {selectedSymbol} closing price</span>
      </div>

      <div className="performance-chart">
        {loading ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            Loading historical prices...
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center px-4 text-center text-sm text-red-300">
            {error}
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            No historical prices are available for this selection.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 12, right: 5, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="historicalGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34D399" stopOpacity={0.24} />
                  <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1E293B" strokeDasharray="3 5" vertical={false} />
              <XAxis
                dataKey="date"
                minTickGap={24}
                tick={{ fill: '#64748B', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                width={70}
                tick={{ fill: '#64748B', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}
              />
              <Tooltip
                contentStyle={{ background: '#101827', border: '1px solid #263347', borderRadius: 12, color: '#E2E8F0' }}
                labelStyle={{ color: '#94A3B8' }}
                formatter={(value) => [formatPrice(value, selectedSymbol), 'Closing price']}
              />
              <Area
                type="monotone"
                dataKey="price"
                name="Closing price"
                stroke="#34D399"
                strokeWidth={2.5}
                fill="url(#historicalGradient)"
                dot={false}
                activeDot={{ r: 4, fill: '#34D399', stroke: '#0B1220', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="chart-footnote">
        <span><i className="status-dot" /> Historical records from local database</span>
        <span>Range: {range}</span>
      </div>
    </div>
  )
}

export default memo(PriceChart)
