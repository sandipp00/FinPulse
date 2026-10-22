import { memo } from 'react'
import { AlertTriangle } from 'lucide-react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useBacktest } from '../hooks/useBacktest'
import { formatPercent } from '../lib/format'

function Stat({ label, value, tone, note }) {
  return (
    <div className="bt-stat">
      <span>{label}</span>
      <strong className={tone ? `tone-${tone}` : ''}>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  )
}

const toneFor = (value) => (value == null ? undefined : value >= 0 ? 'up' : 'down')

// Date.toLocaleString builds a new formatter on every call; the chart axis calls
// this for every label on every render, so reuse one formatter per style.
const dayFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })
const hourFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: '2-digit' })

function formatDate(seconds, interval) {
  const date = new Date(seconds * 1000)
  return (interval === '1d' ? dayFormat : hourFormat).format(date)
}

function BacktestCard({ symbol, interval }) {
  const { data, loading, error } = useBacktest(symbol, interval)

  if (loading) return <div className="bt-card bt-empty">Running backtest for {symbol}...</div>
  if (error) return <div className="bt-card bt-empty bt-error">{error}</div>

  const { trades } = data
  const edge = data.strategy_return_pct - data.buy_hold_return_pct
  const beat = edge >= 0

  return (
    <div className="bt-card">
      <div className="bt-head">
        <div>
          <h3>Historical backtest</h3>
          <p>
            Last {data.period.candles} {interval} candles · long-only · {data.fee_pct}% fee per trade ·
            fills at the next candle&apos;s open
          </p>
        </div>
        <span className={`bt-verdict ${beat ? 'beat' : 'trail'}`}>
          {beat ? 'Beat' : 'Trailed'} buy &amp; hold by {Math.abs(edge).toFixed(1)} pts
        </span>
      </div>

      <div className="bt-stats">
        <Stat label="Strategy return" value={formatPercent(data.strategy_return_pct, 1)} tone={toneFor(data.strategy_return_pct)} />
        <Stat label="Buy & hold" value={formatPercent(data.buy_hold_return_pct, 1)} tone={toneFor(data.buy_hold_return_pct)} />
        <Stat
          label="Win rate"
          value={trades.win_rate_pct == null ? '—' : `${trades.win_rate_pct}%`}
          note={`${trades.count} trade${trades.count === 1 ? '' : 's'}`}
        />
        <Stat
          label="Max drawdown"
          value={formatPercent(data.strategy_max_drawdown_pct, 1)}
          tone="down"
          note={`B&H ${formatPercent(data.buy_hold_max_drawdown_pct, 1)}`}
        />
        <Stat label="Time in market" value={`${data.exposure_pct}%`} />
        <Stat
          label="Sharpe"
          value={data.sharpe_ratio ?? '—'}
          note={data.sharpe_ratio == null ? 'window under 14 days' : 'zero risk-free rate'}
        />
      </div>

      <div className="bt-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.equity_curve} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid stroke="#1E293B" strokeDasharray="3 5" vertical={false} />
            <XAxis
              dataKey="time"
              minTickGap={40}
              tick={{ fill: '#64748B', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) => formatDate(value, interval)}
            />
            <YAxis
              width={54}
              tick={{ fill: '#64748B', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) => `${value}%`}
            />
            <Tooltip
              contentStyle={{ background: '#101827', border: '1px solid #263347', borderRadius: 12, color: '#E2E8F0' }}
              labelStyle={{ color: '#94A3B8' }}
              labelFormatter={(value) => formatDate(value, interval)}
              formatter={(value, name) => [formatPercent(value, 1), name]}
            />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 10, color: '#94A3B8' }} />
            <Line type="monotone" dataKey="strategy" name="Signal strategy" stroke="#34D399" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="buy_hold" name="Buy & hold" stroke="#64748B" strokeWidth={1.5} strokeDasharray="4 4" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {data.sample_warning && (
        <p className="bt-warning">
          <AlertTriangle size={13} /> Only {trades.count} trades: too few to draw conclusions.
        </p>
      )}
      <p className="bt-note">
        A backtest shows how these rules would have done in the past on this one stretch of
        history. It does not predict what happens next.
      </p>
    </div>
  )
}

export default memo(BacktestCard)
