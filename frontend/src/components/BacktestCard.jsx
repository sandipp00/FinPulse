import { memo, useState } from 'react'
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

const SLIPPAGE_BPS = [0, 5, 10, 25]
const POSITION_PCT = [25, 50, 100]

function Choice({ label, options, value, onChange, format }) {
  return (
    <div className="bt-choice">
      <span>{label}</span>
      <div className="range-control" role="group" aria-label={label}>
        {options.map((option) => (
          <button key={option} onClick={() => onChange(option)} className={option === value ? 'range-active' : ''} aria-pressed={option === value}>
            {format(option)}
          </button>
        ))}
      </div>
    </div>
  )
}

function SplitTable({ split, interval }) {
  if (!split) return null
  const rows = [['First 70%', split.in_sample], ['Latest 30%', split.out_of_sample]]
  return (
    <div className="table-scroll">
      <table className="rel-table bt-split">
        <thead>
          <tr><th /><th>From</th><th>To</th><th>Strategy</th><th>Buy &amp; hold</th><th>Trend rule</th><th>Max drawdown</th><th>Trades</th></tr>
        </thead>
        <tbody>
          {rows.map(([label, seg]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{formatDate(seg.start, interval)}</td>
              <td>{formatDate(seg.end, interval)}</td>
              <td className={`num tone-${toneFor(seg.strategy_return_pct)}`}>{formatPercent(seg.strategy_return_pct, 1)}</td>
              <td className="num">{formatPercent(seg.buy_hold_return_pct, 1)}</td>
              <td className="num">{formatPercent(seg.trend_return_pct, 1)}</td>
              <td className="num">{formatPercent(seg.strategy_max_drawdown_pct, 1)}</td>
              <td className="num">{seg.trades}{seg.win_rate_pct != null ? ` · ${seg.win_rate_pct}% won` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="bt-note">{split.note}</p>
    </div>
  )
}

function BacktestCard({ symbol, interval }) {
  const [slippageBps, setSlippageBps] = useState(0)
  const [positionPct, setPositionPct] = useState(100)
  const { data, loading, error } = useBacktest(symbol, interval, { slippageBps, positionPct })

  const controls = (
    <div className="bt-controls">
      <Choice label="Slippage per fill" options={SLIPPAGE_BPS} value={slippageBps} onChange={setSlippageBps} format={(v) => (v ? `${v} bp` : 'none')} />
      <Choice label="Position size" options={POSITION_PCT} value={positionPct} onChange={setPositionPct} format={(v) => `${v}%`} />
    </div>
  )

  if (loading) return <div className="bt-card bt-empty">{controls}Running backtest for {symbol}...</div>
  if (error) return <div className="bt-card bt-empty bt-error">{controls}{error}</div>

  const { trades } = data
  const edge = data.strategy_return_pct - data.buy_hold_return_pct
  const beat = edge >= 0

  return (
    <div className="bt-card">
      <div className="bt-head">
        <div>
          <h3>Historical backtest</h3>
          <p>
            Last {data.period.candles} {interval} candles · long-only · {data.fee_pct}% fee per fill ·
            {data.slippage_pct ? ` ${data.slippage_pct}% slippage per fill ·` : ' no slippage ·'} {data.position_size_pct}% of
            equity per entry · fills at the next candle&apos;s open
          </p>
        </div>
        <span className={`bt-verdict ${beat ? 'beat' : 'trail'}`}>
          {beat ? 'Beat' : 'Trailed'} buy &amp; hold by {Math.abs(edge).toFixed(1)} pts
        </span>
      </div>

      {controls}

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
        <Stat
          label="50/200 trend rule"
          value={formatPercent(data.baselines.trend.return_pct, 1)}
          tone={toneFor(data.baselines.trend.return_pct)}
          note={`${data.baselines.trend.trades} trades · ${data.baselines.trend.exposure_pct}% in market`}
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
            <Line type="monotone" dataKey="trend" name="50/200 trend rule" stroke="#FBBF24" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <SplitTable split={data.split} interval={interval} />
      <p className="bt-note">{data.baselines.trend.note} Fees, slippage and position size apply to every line.</p>

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
